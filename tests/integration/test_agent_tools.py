"""The research agent's tools against an ingested job (fake SEC data, real Postgres retrieval)."""
import pytest

from backend.agent.tools import ToolContext, build_tools, chunk_handle, resolve_handles
from backend.analysis.rerank import NoopReranker
from backend.core.database import SessionLocal
from backend.models import DocumentChunk
from backend.pipeline.base import ProviderBusyError
from tests.fakes import FakeLLM, ingest


@pytest.fixture
def tools(make_job, tmp_path):
    job = ingest(make_job, tmp_path)
    tc = ToolContext(
        job_id=job.id, company="Widgetco Inc.", ticker="WDGT", session_factory=SessionLocal,
        llm=FakeLLM(), reranker=NoopReranker(),
    )
    return tc, {t.name: t for t in build_tools(tc)}


def test_search_returns_handled_passages_and_records_trace(tools):
    tc, by_name = tools

    output = by_name["search_filings"].invoke({"query": "shortage of specialty steel"})

    assert "[P:" in output and "10-K for period ending 2024-09-30" in output
    assert tc.seen and all(h.startswith("P:") for h in tc.seen)
    assert tc.trace[0]["tool"] == "search_filings"
    assert tc.trace[0]["input"] == {"query": "shortage of specialty steel", "form": "any"}
    assert tc.trace[0]["summary"].startswith("4 passages") or "passages" in tc.trace[0]["summary"]


def test_search_with_no_matching_form_says_so(tools):
    _, by_name = tools

    assert "No 10-Q filings" in by_name["search_filings"].invoke({"query": "anything", "form": "10-Q"})


def test_read_passage_by_handle_and_unknown_handle(tools):
    tc, by_name = tools
    with SessionLocal() as session:
        chunk = session.query(DocumentChunk).order_by(DocumentChunk.chunk_index).first()
    handle = chunk_handle(chunk.id)

    output = by_name["read_passage"].invoke({"handle": handle})
    missing = by_name["read_passage"].invoke({"handle": "P:00000000"})

    assert output.startswith(f"[{handle}]") and chunk.content[:60] in output
    assert "No passage" in missing
    with SessionLocal() as session:
        assert set(resolve_handles(session, tc.job_id, [handle, "P:zz", "garbage"])) == {handle}


def test_metrics_and_reported_figures_come_from_code(tools):
    _, by_name = tools

    metrics = by_name["get_metrics"].invoke({"keys": ["operating_margin"]})
    figures = by_name["get_reported_figures"].invoke({"fields": ["revenue"]})

    assert "Operating margin FY2024 = 25.0%" in metrics and "M" in metrics.split(":")[1]
    assert "FY2024 (ended 2024-09-30): revenue $121.00B" in figures


def test_tool_errors_go_to_the_model_but_provider_errors_go_to_the_queue(tools):
    tc, by_name = tools

    class Broken(FakeLLM):
        def embed(self, texts, *, task):
            raise ValueError("bad input")

    class Busy(FakeLLM):
        def embed(self, texts, *, task):
            raise ProviderBusyError("quota")

    tc.llm = Broken()
    assert by_name["search_filings"].invoke({"query": "x"}).startswith("Tool error: bad input")
    tc.llm = Busy()
    with pytest.raises(ProviderBusyError):
        by_name["search_filings"].invoke({"query": "x"})
