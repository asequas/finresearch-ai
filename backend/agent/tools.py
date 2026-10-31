"""The research agent's tools (ADR 0008): read-only views over one job's filings and computed numbers.

Tools are stateless functions of the database, so a researcher that is re-run after a crash sees exactly
what the first run saw. Passages are named by a stable handle derived from the chunk id ("P:1a2b3c4d"),
which survives retries and lets the drafting step load the full passage the researcher relied on.
"""
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from backend.analysis.metrics import format_usd
from backend.analysis.rerank import Reranker
from backend.analysis.retrieval import RetrievedChunk, retrieve
from backend.core.config import settings
from backend.llm.chat import JOB_ERRORS
from backend.llm.client import LLMClient
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.financial_snapshot import MONEY_FIELDS, FinancialSnapshot
from backend.pipeline.research import _job_documents, _metric_lines, _metrics

SEARCH_RESULTS = 4
PREVIEW_CHARS = 1200
PASSAGE_CHARS = 2600


def chunk_handle(chunk_id: UUID) -> str:
    return f"P:{chunk_id.hex[:8]}"


def resolve_handles(session: Session, job_id: UUID, handles: list[str]) -> dict[str, RetrievedChunk]:
    """Load the passages behind handles, restricted to this job's filings. Unknown handles are skipped."""
    prefixes = {h.removeprefix("P:").strip().lower() for h in handles if h.strip().upper().startswith("P:")}
    prefixes = {p for p in prefixes if len(p) == 8 and all(c in "0123456789abcdef" for c in p)}
    if not prefixes:
        return {}
    document_ids = [d.id for d in _job_documents(session, job_id)]
    rows = session.scalars(
        select(DocumentChunk).where(
            DocumentChunk.document_id.in_(document_ids),
            cast(DocumentChunk.id, String).op("~")(f"^({'|'.join(sorted(prefixes))})"),
        )
    )
    found = {}
    for chunk in rows:
        found[chunk_handle(chunk.id)] = RetrievedChunk(
            id=chunk.id, document_id=chunk.document_id, section=chunk.section, content=chunk.content,
            score=0.0, vector_rank=None, keyword_rank=None,
        )
    return found


@dataclass
class ToolContext:
    """What one agent's tools may see. `trace` is private to that agent (researchers run in parallel)."""

    job_id: UUID
    company: str
    ticker: str
    session_factory: Callable[[], Session]
    llm: LLMClient
    reranker: Reranker
    checkpoint: Callable[[], None] = lambda: None
    trace: list[dict] = field(default_factory=list)
    # Handles this agent has been shown, in order; the fallback evidence if it runs out of budget.
    seen: list[str] = field(default_factory=list)

    def _documents(self, session: Session, form: str = "any") -> list[Document]:
        documents = _job_documents(session, self.job_id)
        return [d for d in documents if form == "any" or (d.form_type or "").upper() == form.upper()]

    def _label(self, document: Document | None, chunk_section: str | None) -> str:
        if document is None:
            return chunk_section or "filing"
        period = document.document_date.isoformat() if document.document_date else "n/a"
        return f"{document.form_type or 'filing'} for period ending {period} · {chunk_section or 'unlabelled section'}"


class SearchInput(BaseModel):
    query: str = Field(description="What you need to find, phrased like a question or the words a filing would use")
    form: Literal["any", "10-K", "10-Q"] = Field(
        default="any", description="10-K for annual detail and risk factors, 10-Q for the latest quarter"
    )


class PassageInput(BaseModel):
    handle: str = Field(description="A passage handle exactly as shown by search_filings, e.g. 'P:1a2b3c4d'")


class MetricsInput(BaseModel):
    keys: list[str] = Field(
        default_factory=list,
        description="Optional filters such as 'margin', 'growth', 'free_cash_flow', 'debt'. Empty returns all.",
    )


class FiguresInput(BaseModel):
    fields: list[str] = Field(
        default_factory=list, description=f"Line items to show; any of: {', '.join(MONEY_FIELDS)}. Empty returns the main ones."
    )


def build_tools(tc: ToolContext) -> list[BaseTool]:
    def traced(name: str, run: Callable[..., tuple[str, str]]) -> Callable[..., str]:
        """Record every call, and return failures to the model as text it can act on.

        Control-flow exceptions (lease lost, cancel, provider busy) still propagate: those are the
        job's business, not the model's.
        """

        def call(**kwargs) -> str:
            tc.checkpoint()
            started = time.perf_counter()
            try:
                output, summary = run(**kwargs)
            except JOB_ERRORS:
                raise
            except Exception as exc:
                output, summary = f"Tool error: {exc}. Try different arguments.", f"error: {exc}"[:200]
            tc.trace.append({
                "tool": name, "input": kwargs, "summary": summary,
                "ms": round((time.perf_counter() - started) * 1000),
            })
            return output

        return call

    def search_filings(query: str, form: str = "any") -> tuple[str, str]:
        [embedding] = tc.llm.embed([query], task="query")
        with tc.session_factory() as session:
            documents = tc._documents(session, form)
            if not documents:
                return f"No {form} filings are available for this company.", "no filings"
            by_id = {d.id: d for d in documents}
            hits = retrieve(
                session, query_text=query, query_embedding=embedding, document_ids=list(by_id),
                reranker=tc.reranker, limit=SEARCH_RESULTS, rerank_candidates=settings.rerank_candidates,
                exclude_terms=[tc.company, tc.ticker],
            )
        if not hits:
            return "No passages matched. Rephrase with the words a filing would use.", "0 passages"
        blocks = []
        for hit in hits:
            handle = chunk_handle(hit.id)
            if handle not in tc.seen:
                tc.seen.append(handle)
            text = hit.content if len(hit.content) <= PREVIEW_CHARS else hit.content[:PREVIEW_CHARS] + " …(read_passage for the rest)"
            blocks.append(f"[{handle}] {tc._label(by_id.get(hit.document_id), hit.section)}\n{text}")
        return "\n\n".join(blocks), f"{len(hits)} passages: {', '.join(chunk_handle(h.id) for h in hits)}"

    def read_passage(handle: str) -> tuple[str, str]:
        with tc.session_factory() as session:
            found = resolve_handles(session, tc.job_id, [handle])
            if not found:
                return (f"No passage {handle!r} in this company's filings. Use a handle exactly as search_filings shows it.",
                        "unknown handle")
            [(key, chunk)] = found.items()
            following = session.scalar(
                select(DocumentChunk.content).where(
                    DocumentChunk.document_id == chunk.document_id,
                    DocumentChunk.chunk_index == select(DocumentChunk.chunk_index).where(DocumentChunk.id == chunk.id).scalar_subquery() + 1,
                )
            )
            document = session.get(Document, chunk.document_id)
            label = tc._label(document, chunk.section)
        if key not in tc.seen:
            tc.seen.append(key)
        text = chunk.content + (f"\n\n(continues)\n{following}" if following else "")
        return f"[{key}] {label}\n{text[:PASSAGE_CHARS]}", f"read {key}"

    def get_metrics(keys: list[str] | None = None) -> tuple[str, str]:
        with tc.session_factory() as session:
            metrics = _metrics(session, tc.job_id)
        text, ids = _metric_lines(metrics)
        if keys:
            wanted = [k.lower().replace(" ", "_") for k in keys]
            lines = [
                line for (handle, metric), line in zip(ids.items(), text.splitlines())
                if any(w in metric.metric_key or w in metric.label.lower().replace(" ", "_") for w in wanted)
            ]
            text = "\n".join(lines) or f"No computed metric matches {keys}. Call get_metrics with no filter to see all."
        header = "Computed by code from SEC XBRL (cite by M-handle; never recompute):\n"
        return header + text, f"{len(text.splitlines())} metrics"

    def get_reported_figures(fields: list[str] | None = None) -> tuple[str, str]:
        chosen = [f for f in (fields or []) if f in MONEY_FIELDS] or [
            "revenue", "operating_income", "net_income", "operating_cash_flow", "cash", "debt",
        ]
        with tc.session_factory() as session:
            snapshots = list(session.scalars(
                select(FinancialSnapshot).where(FinancialSnapshot.research_job_id == tc.job_id)
                .order_by(FinancialSnapshot.period_end_date)
            ))
        if not snapshots:
            return "No reported financials were extracted for this company.", "no data"
        rows = []
        for snap in snapshots:
            values = ", ".join(
                f"{name.replace('_', ' ')} {format_usd(getattr(snap, name)) if getattr(snap, name) is not None else 'not reported'}"
                for name in chosen
            )
            rows.append(f"{snap.period} (ended {snap.period_end_date.isoformat()}): {values}")
        note = "Reported XBRL values, for orientation. Claims must cite computed metrics (M-handles) or quoted passages.\n"
        return note + "\n".join(rows), f"{len(snapshots)} periods × {len(chosen)} items"

    specs = [
        ("search_filings", search_filings, SearchInput,
         "Hybrid search (semantic + keyword, reranked) over this company's 10-K/10-Q text. Returns up to 4 "
         "passages, each with a handle like [P:1a2b3c4d], the filing, period and section."),
        ("read_passage", read_passage, PassageInput,
         "Read one passage in full (plus the passage that follows it) by its handle."),
        ("get_metrics", get_metrics, MetricsInput,
         "Metrics computed by code from SEC XBRL (margins, growth, cash flow, leverage), each with an M-handle, "
         "period, value and formula."),
        ("get_reported_figures", get_reported_figures, FiguresInput,
         "Reported line items per fiscal year (revenue, income, cash flow, cash, debt...) from SEC XBRL."),
    ]
    return [
        StructuredTool.from_function(func=traced(name, run), name=name, description=description, args_schema=schema)
        for name, run, schema, description in specs
    ]
