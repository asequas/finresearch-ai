"""'Ask the analyst': a tool-using follow-up agent grounded in one finished report (ADR 0008).

Each question runs a bounded `create_agent` loop over the same read-only tools the researchers used, plus
the report's verified claims. Every quote the answer cites is checked against its filing passage before it
is stored, so the chat is held to the report's standard: an unverified citation is shown as unverified.

`report_chat_messages` is the record of the conversation. The agent is rebuilt from the last few turns on
every question; there is no second copy of the history in a checkpointer.
"""
import re
from collections.abc import Callable
from typing import Literal
from uuid import UUID

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.agent.tools import ToolContext, build_tools, resolve_handles
from backend.analysis.rerank import Reranker, get_reranker
from backend.analysis.verification import quote_in_source, snap_quote
from backend.core.config import settings
from backend.llm.chat import AgentModel, gemini_agent_model
from backend.llm.client import LLMClient, get_llm_client
from backend.models.claim import Claim
from backend.models.document import Document
from backend.models.report import Report
from backend.models.report_chat_message import ReportChatMessage
from backend.models.research_job import ResearchJob
from backend.pipeline.base import PermanentError, ProviderBusyError, RetryableError
from backend.schemas.agent import ChatCitationOut, ChatMessageOut, ChatThreadResponse
from backend.services.errors import LimitReachedError, NotFoundError, UpstreamBusyError

HISTORY_TURNS = 6


class ChatCitation(BaseModel):
    handle: str = Field(description="The passage handle the quote comes from, e.g. 'P:1a2b3c4d'")
    quote: str = Field(description="One sentence copied exactly from that passage")


class ChatAnswer(BaseModel):
    """Call this to answer. Keep it short; cite a passage for every factual statement."""

    answer: str = Field(description="2-6 sentences answering the question, plainly, from the evidence")
    citations: list[ChatCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = Field(description="How well the filings support the answer")


SYSTEM = """You are the analyst who wrote a research report on {company} ({ticker}). Answer the user's follow-up
questions using only the report's verified claims, the company's SEC filings and metrics computed by code.

- Start with get_report_claims when the question is about the report's conclusions.
- Use search_filings / read_passage for anything else; use get_metrics for numbers. Never compute numbers yourself.
- Cite every factual statement with a passage handle and an exact quote from that passage.
- If the filings don't answer the question, say so and set confidence to low. No buy/sell advice.
- You have at most {tool_calls} tool calls. Finish by calling ChatAnswer."""


class AnalystChatService:
    def __init__(
        self,
        agent_model_factory: Callable[[], AgentModel] | None = None,
        llm_factory: Callable[[], LLMClient] = get_llm_client,
        reranker_factory: Callable[[], Reranker] = get_reranker,
    ):
        self.agent_model_factory = agent_model_factory or (lambda: gemini_agent_model(strong=True))
        self.llm_factory = llm_factory
        self.reranker_factory = reranker_factory

    # ---- reads ---------------------------------------------------------------

    def _job_with_report(self, session: Session, job_id: UUID, user_id: UUID) -> tuple[ResearchJob, Report]:
        job = session.scalar(select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id))
        if job is None:
            raise NotFoundError("Research job not found")
        report = session.scalar(select(Report).where(Report.research_job_id == job_id))
        if report is None:
            raise NotFoundError("This job has no report yet, so there is nothing to ask about")
        return job, report

    def get_thread(self, session: Session, *, job_id: UUID, user_id: UUID) -> ChatThreadResponse:
        _, report = self._job_with_report(session, job_id, user_id)
        messages = list(session.scalars(
            select(ReportChatMessage).where(ReportChatMessage.research_job_id == job_id)
            .order_by(ReportChatMessage.created_at, ReportChatMessage.role.desc())
        ))
        asked = sum(1 for m in messages if m.role == "user")
        suggestions = [] if messages else list((report.full_report or {}).get("open_questions", []))[:3]
        return ChatThreadResponse(
            job_id=job_id,
            messages=[ChatMessageOut(
                id=m.id, role=m.role, content=m.content, citations=m.citations or [], tool_steps=m.tool_steps or [],
                model=m.model, created_at=m.created_at,
            ) for m in messages],
            turns_left=max(0, settings.chat_max_turns - asked),
            suggestions=suggestions,
        )

    # ---- one turn ----------------------------------------------------------------

    def ask(self, session: Session, *, job_id: UUID, user_id: UUID, question: str) -> ChatThreadResponse:
        job, report = self._job_with_report(session, job_id, user_id)
        asked = session.scalar(
            select(func.count()).select_from(ReportChatMessage)
            .where(ReportChatMessage.research_job_id == job_id, ReportChatMessage.role == "user")
        )
        if asked >= settings.chat_max_turns:
            raise LimitReachedError(f"This report has used its {settings.chat_max_turns} questions.")
        history = list(session.scalars(
            select(ReportChatMessage).where(ReportChatMessage.research_job_id == job_id)
            .order_by(ReportChatMessage.created_at.desc(), ReportChatMessage.role).limit(HISTORY_TURNS * 2)
        ))[::-1]
        # The read above opened a transaction; end it so no connection is held idle during model calls.
        session.rollback()

        tool_ctx = ToolContext(
            job_id=job_id, company=job.company, ticker=job.ticker, session_factory=_session_factory(session),
            llm=self.llm_factory(), reranker=self.reranker_factory(),
        )
        try:
            answer, model_name = self._run_agent(job, report, tool_ctx, history, question)
        except ProviderBusyError as exc:
            raise UpstreamBusyError(f"{exc} Try again in a minute.") from exc
        except (RetryableError, PermanentError) as exc:
            raise UpstreamBusyError(f"The analyst couldn't answer right now: {exc}") from exc

        citations = self._verify(session, job_id, answer.citations)
        # One transaction per turn: the question and its answer are stored together or not at all.
        session.add(ReportChatMessage(research_job_id=job_id, role="user", content=question.strip()))
        session.flush()
        session.add(ReportChatMessage(
            research_job_id=job_id, role="assistant", content=answer.answer.strip(),
            citations=[c.model_dump() for c in citations], tool_steps=tool_ctx.trace, model=model_name,
        ))
        session.commit()
        return self.get_thread(session, job_id=job_id, user_id=user_id)

    def _run_agent(self, job, report, tool_ctx, history, question) -> tuple[ChatAnswer, str]:
        claims_text = _claims_digest(tool_ctx, report)

        def get_report_claims() -> str:
            tool_ctx.trace.append({"tool": "get_report_claims", "input": {}, "summary": "report summary and claims", "ms": 0})
            return claims_text

        agent_model = self.agent_model_factory()
        tools = [
            StructuredTool.from_function(
                func=get_report_claims, name="get_report_claims",
                description="The report's headline, direct answer and its verified claims (with verdicts).",
            ),
            *build_tools(tool_ctx),
        ]
        agent = create_agent(
            agent_model.model, tools,
            system_prompt=SYSTEM.format(company=job.company, ticker=job.ticker, tool_calls=settings.chat_tool_calls),
            middleware=[
                *agent_model.middleware,
                ToolCallLimitMiddleware(run_limit=settings.chat_tool_calls, exit_behavior="continue"),
                ModelCallLimitMiddleware(run_limit=settings.chat_tool_calls + 2, exit_behavior="end"),
            ],
            response_format=ToolStrategy(ChatAnswer),
            name="analyst_chat",
        )
        messages = []
        for turn in history:
            messages.append(HumanMessage(turn.content) if turn.role == "user" else AIMessage(turn.content))
        messages.append(HumanMessage(question))
        result = agent.invoke({"messages": messages}, {"recursion_limit": 4 * settings.chat_tool_calls + 10})
        answer = result.get("structured_response")
        if answer is None:
            answer = ChatAnswer(
                answer="I couldn't reach a supported answer within my research budget. Try a narrower question.",
                citations=[], confidence="low",
            )
        model_name = next(
            (m.response_metadata.get("model_name") for m in reversed(result.get("messages", []))
             if isinstance(m, AIMessage) and m.response_metadata.get("model_name")),
            agent_model.name,
        )
        return answer, model_name

    def _verify(self, session: Session, job_id: UUID, citations: list[ChatCitation]) -> list[ChatCitationOut]:
        """Check each cited quote against its passage; snap near-verbatim quotes to the filing's words."""
        def key(handle: str) -> str:
            # Models sometimes pack extra text into the field ("P:8272934b,quote:"); the handle is the 8 hex digits.
            match = re.search(r"(?:p:)?\s*([0-9a-f]{8})\b", handle.strip().lower())
            return f"P:{match.group(1)}" if match else handle.strip()

        resolved = resolve_handles(session, job_id, [key(c.handle) for c in citations])
        documents = {d.id: d for d in session.scalars(select(Document).where(
            Document.id.in_([chunk.document_id for chunk in resolved.values()])
        ))} if resolved else {}
        out = []
        for citation in citations:
            handle = key(citation.handle)
            chunk = resolved.get(handle)
            quote, verified = citation.quote.strip(), False
            if chunk is not None:
                verified = quote_in_source(quote, chunk.content)
                if not verified:
                    exact = snap_quote(quote, chunk.content)
                    if exact is not None:
                        quote, verified = exact, True
            document = documents.get(chunk.document_id) if chunk else None
            out.append(ChatCitationOut(
                handle=handle, quote=quote, verified=verified,
                section=chunk.section if chunk else None,
                form=document.form_type if document else None,
                period=document.document_date.isoformat() if document and document.document_date else None,
                url=document.url if document else None,
            ))
        session.rollback()
        return out


def _session_factory(session: Session):
    """Tools open their own short sessions on the same engine (they may run while the request session idles)."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def _claims_digest(tool_ctx: ToolContext, report: Report) -> str:
    with tool_ctx.session_factory() as session:
        claims = list(session.scalars(
            select(Claim).where(Claim.research_job_id == tool_ctx.job_id).order_by(Claim.position)
        ))
    full = report.full_report or {}
    lines = [f"Headline: {full.get('headline', '')}", f"Direct answer: {full.get('direct_answer', '')}", "Claims:"]
    lines += [f"{c.position + 1}. [{c.verification_status}] {c.claim_text}" for c in claims]
    return "\n".join(lines)
