"""Reads the research agent's trace back out of agent_runs (ADR 0008)."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.agent_run import AgentRun
from backend.models.research_job import ResearchJob
from backend.schemas.agent import AgentTraceResponse, PlannedQuestionOut, ResearcherOut, RoundOut, TraceTotals
from backend.services.errors import NotFoundError


class AgentTraceService:
    def get_trace(self, session: Session, *, job_id: UUID, user_id: UUID) -> AgentTraceResponse:
        job = session.scalar(select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id))
        if job is None:
            raise NotFoundError("Research job not found")
        runs = list(session.scalars(
            select(AgentRun).where(AgentRun.research_job_id == job_id).order_by(AgentRun.started_at, AgentRun.id)
        ))
        names = {r.agent_name for r in runs}
        mode = "agent" if "planning" in names else "linear" if "analyzing" in names else "pending"

        planning = [r for r in runs if r.agent_name == "planning" and r.status == "completed"]
        plan = [PlannedQuestionOut(**q) for q in (planning[-1].extra_metadata or {}).get("questions", [])] if planning else []

        researchers = []
        for run in runs:
            if run.agent_name != "researching":
                continue
            meta = run.extra_metadata or {}
            if not meta.get("question"):
                continue  # a failed attempt recorded before runs carried their task; its retry is listed instead
            researchers.append(ResearcherOut(
                task_id=meta.get("task_id", "?"), kind=meta.get("kind", "question"), question=meta.get("question", ""),
                round=meta.get("round", 0), status=run.status, attempt=run.attempt, started_at=run.started_at,
                duration_ms=run.duration_ms, answer=meta.get("answer"), notes=meta.get("notes"),
                gaps=meta.get("gaps", []), dropped_handles=meta.get("dropped_handles", []),
                tool_calls=meta.get("tool_calls", []), model=run.model, input_tokens=run.input_tokens,
                output_tokens=run.output_tokens, error_message=run.error_message,
            ))
        # A researcher retried after a crash appears once per attempt; show the latest attempt of each task.
        latest: dict[tuple[str, int], ResearcherOut] = {}
        for r in researchers:
            latest[(r.task_id, r.round)] = r
        researchers = list(latest.values())

        rounds: dict[tuple[int, bool], RoundOut] = {}
        for run in runs:
            meta = run.extra_metadata or {}
            if run.status != "completed" or "revision" not in meta:
                continue
            restored = bool(meta.get("restored"))
            entry = rounds.setdefault((meta["revision"], restored), RoundOut(revision=meta["revision"], restored=restored))
            if run.agent_name == "verifying":
                entry.verdicts = meta.get("verdicts", {})
            elif run.agent_name == "critic":
                entry.decision, entry.reason, entry.gaps = meta.get("decision"), meta.get("reason"), meta.get("gaps", [])

        totals = TraceTotals(
            researchers=len(researchers),
            tool_calls=sum(len(r.tool_calls) for r in researchers),
            revisions=sum(1 for r in rounds.values() if r.decision == "revise"),
            input_tokens=sum(r.input_tokens or 0 for r in runs),
            output_tokens=sum(r.output_tokens or 0 for r in runs),
        )
        return AgentTraceResponse(
            job_id=job_id, mode=mode, plan=plan, researchers=researchers,
            rounds=[rounds[k] for k in sorted(rounds)], totals=totals,
        )
