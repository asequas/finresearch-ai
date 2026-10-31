"""The research agent: a LangGraph StateGraph run inside the durable job queue (ADR 0008).

    plan ──Send×N──▶ researcher ──▶ draft ──▶ verify ──▶ critic ──▶ synthesize
                      ▲ (tool-using agents)                    │
                      └────────── Send×gaps (≤ max_revisions) ─┘

- The planner and the drafting/judging/synthesis steps are single structured LLM calls.
- Each researcher is a LangChain `create_agent` loop with read-only tools and hard call budgets.
- The critic is code, not a model: it routes on the verifier's verdicts, so the loop is explainable and bounded.
- State holds only JSON (plans, findings, verdict summaries). Claims, evidence and the report are written to
  their own tables through fenced transactions; the checkpoint lets a retried job resume at the node that failed.
"""
import logging
import operator
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy import select

from backend.agent import prompts as agent_prompts
from backend.agent.context import CompactToolResults
from backend.agent.tools import ToolContext, build_tools, chunk_handle, resolve_handles
from backend.analysis.retrieval import RetrievedChunk, retrieve
from backend.core.config import settings
from backend.costs.ledger import usage_scope
from backend.models.document_chunk import DocumentChunk
from backend.models.research_job import ResearchStage
from backend.pipeline import prompts
from backend.pipeline.base import JobContext, LeaseLost, StageUsage
from backend.pipeline.research import (
    MAX_EXCERPTS,
    Services,
    _job_documents,
    _latest_period_end,
    _metric_lines,
    _metrics,
    _record,
    excerpt_block,
    save_claims,
    verify_claims,
    write_report,
)
from backend.services.job_queue import JobQueueService

logger = logging.getLogger(__name__)

# Fraction of the agent's progress range at which each node starts.
_PROGRESS = {
    ResearchStage.PLANNING: 0.0,
    ResearchStage.RESEARCHING: 0.1,
    ResearchStage.DRAFTING: 0.55,
    ResearchStage.VERIFYING: 0.7,
    ResearchStage.SYNTHESIZING: 0.85,
}
GAP_STATUSES = ("unsupported", "partially_supported")


class ResearchState(TypedDict, total=False):
    plan: list[dict]  # [{id, question, focus, approach}]
    findings: Annotated[list[dict], operator.add]  # one per researcher run, every round
    revision: int  # completed critic-driven research rounds
    feedback: list[dict]  # the claims the critic sent back, shown to the next draft
    verify_rounds: Annotated[list[dict], operator.add]  # verdict counts after each verify pass
    # Every draft as written (claims + which chunk each excerpt id meant), so a worse revision can be undone.
    drafts: Annotated[list[dict], operator.add]
    decision: str  # the critic's last decision: "revise", "restore" or "finish"
    restored_from: int  # the revision whose draft was put back, if any


def draft_score(verify_round: dict) -> tuple[float, int]:
    """How well a draft verified: material claims first (partial support counts half), then all supported."""
    material = [c for c in verify_round["claims"] if c["importance"] >= 2]
    weighted = sum(1.0 if c["status"] == "supported" else 0.5 if c["status"] == "partially_supported" else 0.0 for c in material)
    return weighted, sum(1 for c in verify_round["claims"] if c["status"] == "supported")


class ResearcherTask(TypedDict):
    task_id: str
    kind: str  # "question" or "gap"
    question: str
    focus: str
    prompt: str
    round: int


@dataclass
class AgentDeps:
    ctx: JobContext
    services: Services
    queue: JobQueueService
    progress: tuple[int, int]

    def percent(self, stage: ResearchStage) -> int:
        start, end = self.progress
        return min(99, start + int((end - start) * _PROGRESS.get(stage, 0.0)))


@contextmanager
def tracked(deps: AgentDeps, stage: ResearchStage, *, name: str | None = None, bind_usage: bool = True) -> Iterator[StageUsage]:
    """Run one node as a visible, fenced unit: lease check, stage + progress, and an agent_runs row.

    `bind_usage=False` for nodes that run in parallel (researchers): they must not share ctx.usage.
    """
    ctx = deps.ctx
    ctx.checkpoint()
    if not deps.queue.set_stage(ctx.job_id, ctx.lease_token, stage=stage, progress=deps.percent(stage)):
        raise LeaseLost(f"Lease lost for job {ctx.job_id}")
    run_id = deps.queue.start_stage_run(ctx.job_id, ctx.lease_token, stage=stage, attempt=ctx.attempt, agent_name=name)
    if run_id is None:
        raise LeaseLost(f"Lease lost for job {ctx.job_id}")
    usage = StageUsage()
    if bind_usage:
        ctx.usage = usage
    started = datetime.now(timezone.utc)
    try:
        with usage_scope(job_id=ctx.job_id, source="job", stage=name or stage.value):
            yield usage
    except BaseException as exc:
        deps.queue.finish_stage_run(
            run_id, status="failed", started=started, error_message=f"{type(exc).__name__}: {exc}"[:2000],
            model=usage.model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            metadata=usage.metadata,
        )
        raise
    deps.queue.finish_stage_run(
        run_id, status="completed", started=started, model=usage.model, input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens, metadata=usage.metadata,
    )


def _round_robin(lists: list[list[str]], limit: int) -> list[str]:
    """Every source gets its first item before any gets its second."""
    out: list[str] = []
    for rank in range(max((len(l) for l in lists), default=0)):
        for items in lists:
            if rank < len(items) and items[rank] not in out and len(out) < limit:
                out.append(items[rank])
    return out


def build_graph(deps: AgentDeps) -> StateGraph:
    ctx, services = deps.ctx, deps.services

    # ---- plan -------------------------------------------------------------
    def plan(state: ResearchState) -> dict:
        with tracked(deps, ResearchStage.PLANNING) as usage:
            with ctx.session_factory() as session:
                period_end = _latest_period_end(session, ctx.job_id)
            result = services.llm.generate_json(
                prompt=agent_prompts.PLAN_PROMPT.format(
                    query=ctx.query, company=ctx.company, ticker=ctx.ticker, period_end=period_end,
                    min_q=min(3, settings.agent_max_researchers), max_q=settings.agent_max_researchers,
                ),
                schema=agent_prompts.AgentPlan,
                system=prompts.ANALYST_SYSTEM,
            )
            _record(ctx, result)
            questions = [
                {"id": f"q{i}", **q.model_dump()}
                for i, q in enumerate(result.value.questions[: settings.agent_max_researchers], start=1)
            ] or [{"id": "q1", "question": ctx.query, "focus": "business", "approach": "Search the filings."}]
            usage.metadata = {"questions": questions}
        return {"plan": questions, "revision": 0}

    def dispatch_plan(state: ResearchState) -> list[Send]:
        return [
            Send("researcher", ResearcherTask(
                task_id=q["id"], kind="question", question=q["question"], focus=q["focus"], round=0,
                prompt=agent_prompts.RESEARCH_TASK.format(query=ctx.query, **{k: q[k] for k in ("question", "focus", "approach")}),
            ))
            for q in state["plan"]
        ]

    # ---- researcher (one tool-using agent per task, run in parallel) --------
    def researcher(task: ResearcherTask) -> dict:
        with tracked(deps, ResearchStage.RESEARCHING, bind_usage=False) as usage:
            tool_ctx = ToolContext(
                job_id=ctx.job_id, company=ctx.company, ticker=ctx.ticker, session_factory=ctx.session_factory,
                llm=services.llm, reranker=services.reranker, checkpoint=ctx.checkpoint,
            )
            agent_model = services.agent_model()
            agent = create_agent(
                agent_model.model,
                build_tools(tool_ctx),
                system_prompt=agent_prompts.RESEARCHER_SYSTEM.format(
                    company=ctx.company, ticker=ctx.ticker, tool_calls=settings.agent_tool_calls_per_researcher,
                ),
                middleware=[
                    CompactToolResults(),
                    *agent_model.middleware,
                    # Past the budget, tool calls are refused and the model must answer with what it has.
                    ToolCallLimitMiddleware(run_limit=settings.agent_tool_calls_per_researcher, exit_behavior="continue"),
                    ModelCallLimitMiddleware(run_limit=settings.agent_model_calls_per_researcher, exit_behavior="end"),
                ],
                response_format=ToolStrategy(agent_prompts.Findings),
                name="researcher",
            )
            started = time.perf_counter()
            # Known before the call, so a researcher that fails still shows what it was doing and how far it got.
            usage.metadata = {
                "task_id": task["task_id"], "kind": task["kind"], "question": task["question"], "round": task["round"],
                "tool_calls": tool_ctx.trace,
            }
            result = agent.invoke(
                {"messages": [HumanMessage(task["prompt"])]},
                {"recursion_limit": 4 * settings.agent_model_calls_per_researcher + 5},
            )
            for message in result.get("messages", []):
                if isinstance(message, AIMessage) and message.usage_metadata:
                    usage.add_llm_call(
                        model=message.response_metadata.get("model_name") or agent_model.name or "chat-model",
                        input_tokens=message.usage_metadata.get("input_tokens", 0),
                        output_tokens=message.usage_metadata.get("output_tokens", 0),
                    )
            findings = result.get("structured_response")
            seen = set(tool_ctx.seen)
            invented: list[str] = []
            if findings is not None and not tool_ctx.trace:
                # Seen live: a model "answered" from memory without one tool call. Nothing it says is evidence.
                invented = [p for note in findings.notes for p in note.passages]
                finding = {"answer": "", "notes": [], "fallback_passages": [],
                           "gaps": ["The researcher answered without consulting the filings, so its answer was discarded."]}
            elif findings is None:
                # Budget ran out before the researcher concluded: keep what it looked at, say so.
                finding = {"answer": "", "notes": [], "gaps": ["The researcher ran out of budget before concluding."],
                           "fallback_passages": tool_ctx.seen[:4]}
            else:
                notes = []
                for note in findings.notes:
                    # Only handles a tool actually returned count; invented ones are dropped here, not trusted.
                    passages = [p for p in note.passages if p in seen]
                    invented += [p for p in note.passages if p not in seen]
                    notes.append({"text": note.text, "passages": passages, "metrics": note.metrics})
                finding = {"answer": findings.answer, "notes": notes, "gaps": findings.gaps, "fallback_passages": []}
            finding.update(task_id=task["task_id"], kind=task["kind"], question=task["question"],
                           focus=task["focus"], round=task["round"])
            usage.metadata.update(
                answer=finding["answer"], notes=len(finding["notes"]), gaps=finding["gaps"], dropped_handles=invented,
                ms=round((time.perf_counter() - started) * 1000),
            )
        return {"findings": [finding]}

    # ---- draft --------------------------------------------------------------
    def draft(state: ResearchState) -> dict:
        with tracked(deps, ResearchStage.DRAFTING) as usage:
            findings = state.get("findings", [])
            per_finding = [
                [p for note in f["notes"] for p in note["passages"]] or f.get("fallback_passages", [])
                for f in sorted(findings, key=lambda f: -f["round"])  # the latest round's evidence first
            ]
            handles = _round_robin(per_finding, MAX_EXCERPTS)
            with ctx.session_factory() as session:
                documents = _job_documents(session, ctx.job_id)
                metric_text, metric_ids = _metric_lines(_metrics(session, ctx.job_id))
                resolved = resolve_handles(session, ctx.job_id, handles)
                chunks: list[RetrievedChunk] = [resolved[h] for h in handles if h in resolved]
                if not chunks:
                    # Every researcher came back empty-handed: fall back to one plain retrieval of the request.
                    [embedding] = services.llm.embed([ctx.query], task="query")
                    chunks = retrieve(
                        session, query_text=ctx.query, query_embedding=embedding, document_ids=[d.id for d in documents],
                        reranker=services.reranker, limit=8, rerank_candidates=settings.rerank_candidates,
                        exclude_terms=[ctx.company, ctx.ticker],
                    )
            excerpt_text, excerpt_ids = excerpt_block(chunks)
            eid_by_handle = {chunk_handle(chunk.id): eid for eid, chunk in excerpt_ids.items()}

            def cite(note: dict) -> str:
                refs = [eid_by_handle[p] for p in note["passages"] if p in eid_by_handle] + note["metrics"]
                return f"  - {note['text']}" + (f" ({', '.join(refs)})" if refs else "")

            notes = "\n".join(
                f"Q: {f['question']}\nA: {f['answer'] or '(no conclusion)'}\n" + "\n".join(cite(n) for n in f["notes"])
                + (f"\n  Not found: {'; '.join(f['gaps'])}" if f["gaps"] else "")
                for f in findings
            ) or "(no research notes)"
            feedback = state.get("feedback") or []
            feedback_text = agent_prompts.FEEDBACK_BLOCK.format(
                items="\n".join(f'- "{g["text"]}": {g["note"]}' for g in feedback if g["kind"] == "claim")
            ) if any(g["kind"] == "claim" for g in feedback) else ""

            result = services.llm.generate_json(
                prompt=agent_prompts.AGENT_DRAFT_PROMPT.format(
                    query=ctx.query, company=ctx.company, ticker=ctx.ticker, metrics=metric_text,
                    excerpts=excerpt_text or "(no excerpts retrieved)", sections=", ".join(prompts.SECTIONS),
                    notes=notes, feedback=feedback_text,
                ),
                schema=prompts.ClaimDraft,
                system=prompts.ANALYST_SYSTEM,
                strong=True,
            )
            _record(ctx, result)
            save_claims(ctx, result.value, excerpt_ids, metric_ids, documents)
            usage.metadata = {
                "revision": state.get("revision", 0), "excerpts": len(chunks), "claims": len(result.value.claims),
                "findings": len(findings), "feedback": len(feedback),
            }
        return {"drafts": [{
            "revision": state.get("revision", 0),
            "claims": result.value.model_dump(),
            "excerpts": {eid: [str(chunk.id), chunk.rerank_score] for eid, chunk in excerpt_ids.items()},
        }]}

    # ---- restore (undo a revision that verified worse) ------------------------------
    def restore(state: ResearchState) -> dict:
        with tracked(deps, ResearchStage.DRAFTING, name="restore") as usage:
            target = state["restored_from"]
            best = next(d for d in state["drafts"] if d["revision"] == target)
            with ctx.session_factory() as session:
                documents = _job_documents(session, ctx.job_id)
                _, metric_ids = _metric_lines(_metrics(session, ctx.job_id))  # same order as when drafted
                chunks = {c.id: c for c in session.scalars(
                    select(DocumentChunk).where(DocumentChunk.id.in_([UUID(cid) for cid, _ in best["excerpts"].values()]))
                )}
            excerpt_ids = {
                eid: RetrievedChunk(id=chunk.id, document_id=chunk.document_id, section=chunk.section, content=chunk.content,
                                    score=0.0, vector_rank=None, keyword_rank=None, rerank_score=rerank)
                for eid, (cid, rerank) in best["excerpts"].items()
                if (chunk := chunks.get(UUID(cid))) is not None
            }
            save_claims(ctx, prompts.ClaimDraft.model_validate(best["claims"]), excerpt_ids, metric_ids, documents)
            usage.metadata = {"revision": state.get("revision", 0), "restored_from": target}
        return {}

    # ---- verify ---------------------------------------------------------------
    def verify(state: ResearchState) -> dict:
        with tracked(deps, ResearchStage.VERIFYING) as usage:
            outcome = verify_claims(ctx, services.llm)
            restored = state.get("restored_from") is not None
            usage.metadata = {**outcome.metadata(), "revision": state.get("revision", 0), "restored": restored}
        return {"verify_rounds": [{
            "revision": state.get("revision", 0), "restored": restored, "counts": outcome.counts,
            "claims": [{k: c[k] for k in ("id", "text", "importance", "status", "note")} for c in outcome.claims],
        }]}

    # ---- critic (deterministic router) ------------------------------------------
    def critic(state: ResearchState) -> dict:
        with tracked(deps, ResearchStage.VERIFYING, name="critic") as usage:
            latest = state["verify_rounds"][-1]
            revision = state.get("revision", 0)
            if state.get("restored_from") is not None:
                usage.metadata = {"decision": "finish", "revision": revision, "gaps": [], "restored": True,
                                  "reason": f"kept the draft from round {state['restored_from']}, which verified better"}
                return {"decision": "finish", "feedback": []}
            # A revision must never make the report worse: if it verified below an earlier draft, put that one back.
            earlier = [r for r in state["verify_rounds"][:-1] if not r.get("restored")]
            if earlier:
                best = max(earlier, key=draft_score)
                if draft_score(best) > draft_score(latest):
                    reason = (f"the revised draft had {draft_score(latest)[0]:g} important claims supported against "
                              f"{draft_score(best)[0]:g} before, so the round {best['revision']} draft is restored")
                    usage.metadata = {"decision": "restore", "reason": reason, "gaps": [], "revision": revision}
                    return {"decision": "restore", "feedback": [], "restored_from": best["revision"]}
            gaps = [
                {"kind": "claim", "text": c["text"], "note": c["note"], "claim_id": c["id"]}
                for c in latest["claims"]
                if c["importance"] >= 2 and c["status"] in GAP_STATUSES
            ]
            answered = {f["task_id"] for f in state.get("findings", []) if f["notes"]}
            if state.get("revision", 0) == 0:
                gaps += [
                    {"kind": "question", "text": q["question"], "note": "The researcher found no usable evidence.",
                     "task_id": q["id"], "focus": q["focus"]}
                    for q in state.get("plan", []) if q["id"] not in answered
                ]
            gaps = gaps[: settings.agent_max_researchers]
            decision = "revise" if gaps and revision < settings.agent_max_revisions else "finish"
            claims_failing = sum(1 for g in gaps if g["kind"] == "claim")
            questions_empty = len(gaps) - claims_failing
            what = " and ".join(part for part in (
                f"{claims_failing} important {'claim' if claims_failing == 1 else 'claims'} failed verification" if claims_failing else "",
                f"{questions_empty} {'question' if questions_empty == 1 else 'questions'} found no evidence" if questions_empty else "",
            ) if part)
            reason = (
                f"{what}; starting research round {revision + 1}" if decision == "revise"
                else "every important claim is supported" if not gaps
                else f"{what}, but the revision budget ({settings.agent_max_revisions} round) is used up"
            )
            usage.metadata = {"decision": decision, "reason": reason, "gaps": gaps, "revision": revision}
        update: dict[str, Any] = {"decision": decision, "feedback": gaps}
        if decision == "revise":
            update["revision"] = revision + 1
        return update

    def after_critic(state: ResearchState) -> list[Send] | str:
        if state.get("decision") == "restore":
            return "restore"
        if state.get("decision") != "revise":
            return "synthesize"
        sends = []
        for i, gap in enumerate(state["feedback"], start=1):
            if gap["kind"] == "claim":
                prompt = agent_prompts.GAP_TASK.format(query=ctx.query, claim=gap["text"], note=gap["note"])
                question, focus = f"Verify: {gap['text']}", "risks"
            else:
                prompt = agent_prompts.RESEARCH_TASK.format(
                    query=ctx.query, question=gap["text"], focus=gap["focus"],
                    approach="Try different terms than before; read passages in full.",
                )
                question, focus = gap["text"], gap["focus"]
            sends.append(Send("researcher", ResearcherTask(
                task_id=f"r{state['revision']}g{i}", kind="gap" if gap["kind"] == "claim" else "question",
                question=question, focus=focus, prompt=prompt, round=state["revision"],
            )))
        return sends

    # ---- synthesize --------------------------------------------------------------
    def synthesize(state: ResearchState) -> dict:
        with tracked(deps, ResearchStage.SYNTHESIZING):
            findings = state.get("findings", [])
            write_report(ctx, services.llm, research={
                "mode": "agent",
                "questions": [q["question"] for q in state.get("plan", [])],
                "researchers": len(findings),
                "revisions": state.get("revision", 0),
                "verify_rounds": [{"revision": r["revision"], "restored": r.get("restored", False), "counts": r["counts"]}
                                  for r in state.get("verify_rounds", [])],
                "restored_from": state.get("restored_from"),
            })
        return {}

    graph = StateGraph(ResearchState)
    graph.add_node("plan", plan)
    graph.add_node("researcher", researcher)
    graph.add_node("draft", draft)
    graph.add_node("verify", verify)
    graph.add_node("critic", critic)
    graph.add_node("restore", restore)
    graph.add_node("synthesize", synthesize)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", dispatch_plan, ["researcher"])
    graph.add_edge("researcher", "draft")
    graph.add_edge("draft", "verify")
    graph.add_edge("verify", "critic")
    graph.add_conditional_edges("critic", after_critic, ["researcher", "restore", "synthesize"])
    graph.add_edge("restore", "verify")
    graph.add_edge("synthesize", END)
    return graph


@dataclass
class ResearchAgent:
    """Runner stage that executes the graph with a Postgres checkpointer keyed by job id.

    On a retry the graph resumes at the node that failed; finished researchers are not re-run.
    """

    services: Services
    name: ResearchStage = ResearchStage.SYNTHESIZING  # the graph's last node marks the stage done
    weight: int = 50
    reports_own_stages: bool = True
    checkpointer_factory: Any = None

    def run(self, ctx: JobContext, *, queue: JobQueueService, progress: tuple[int, int]) -> None:
        from backend.agent.checkpoint import get_checkpointer

        checkpointer = (self.checkpointer_factory or get_checkpointer)()
        graph = build_graph(AgentDeps(ctx=ctx, services=self.services, queue=queue, progress=progress)).compile(
            checkpointer=checkpointer
        )
        thread_id = str(ctx.job_id)
        config = {
            "configurable": {"thread_id": thread_id},
            "max_concurrency": settings.agent_max_concurrency,
            "recursion_limit": 60,
        }
        snapshot = graph.get_state(config)
        if snapshot.next:
            logger.info("job %s: resuming agent graph at %s", ctx.job_id, ", ".join(snapshot.next))
            graph.invoke(None, config)
        else:
            if snapshot.values:  # a finished thread whose cleanup didn't happen: start over
                checkpointer.delete_thread(thread_id)
            graph.invoke({"revision": 0}, config)
        checkpointer.delete_thread(thread_id)
