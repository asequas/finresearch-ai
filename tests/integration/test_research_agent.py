"""The LangGraph research agent inside the durable queue: routing, bounds, resume and cancellation."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models import AgentRun, Claim, Report, ResearchJob
from backend.models.research_job import ResearchJobStatus
from backend.pipeline.research import Services, research_stages
from backend.worker.main import Worker
from tests.fakes import FakeLLM, FakeSec, ScriptedResearcher, scripted_agent_model


def _worker(tmp_path, model: ScriptedResearcher) -> Worker:
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM,
                        agent_model_factory=scripted_agent_model(model))
    return Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0, busy_retry_base_seconds=0)


def _runs(job_id, name=None):
    with SessionLocal() as session:
        query = select(AgentRun).where(AgentRun.research_job_id == job_id).order_by(AgentRun.started_at)
        if name:
            query = query.where(AgentRun.agent_name == name)
        return list(session.scalars(query))


def _checkpoints(job_id) -> int:
    with SessionLocal() as session:
        return session.execute(text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"), {"t": str(job_id)}).scalar()


def test_agent_plans_researches_self_corrects_once_and_reports(make_job, tmp_path):
    model = ScriptedResearcher()
    job = make_job(ticker="WDGT")

    _worker(tmp_path, model).run_once()

    with SessionLocal() as session:
        job = session.get(ResearchJob, job.id)
        assert job.status == ResearchJobStatus.COMPLETED, job.error_message
        report = session.scalar(select(Report).where(Report.research_job_id == job.id))
    research = report.full_report["research"]
    assert research["mode"] == "agent" and research["questions"] == ["What are the main risks?", "How is profitability trending?"]

    # Round 0: one researcher per planned question. The draft has an important claim with a fabricated
    # quote, so the critic sends it back for one targeted research round, then stops at the budget.
    researchers = _runs(job.id, "researching")
    assert [r.extra_metadata["round"] for r in researchers].count(0) == 2
    assert [r.extra_metadata["kind"] for r in researchers if r.extra_metadata["round"] == 1] == ["gap"]
    assert all(r.extra_metadata["tool_calls"][0]["tool"] == "search_filings" for r in researchers)
    critic = [r.extra_metadata for r in _runs(job.id, "critic")]
    assert [c["decision"] for c in critic] == ["revise", "finish"]
    assert "revision budget" in critic[1]["reason"]
    assert research["revisions"] == 1 and len(research["verify_rounds"]) == 2
    assert len(_runs(job.id, "drafting")) == 2 and len(_runs(job.id, "verifying")) == 2

    # Invented handles never reach the evidence: the researcher cited P:deadbeef, which no tool returned.
    assert all(r.extra_metadata["dropped_handles"] == ["P:deadbeef"] for r in researchers)
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Claim).where(Claim.research_job_id == job.id)) == 4
    assert _checkpoints(job.id) == 0  # working memory is dropped once the record is written


def test_revision_budget_zero_skips_the_loop(make_job, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_revisions", 0)
    job = make_job(ticker="WDGT")

    _worker(tmp_path, ScriptedResearcher()).run_once()

    assert [r.extra_metadata["decision"] for r in _runs(job.id, "critic")] == ["finish"]
    assert len(_runs(job.id, "researching")) == 2


def test_busy_provider_mid_fanout_resumes_without_redoing_finished_researchers(make_job, tmp_path):
    model = ScriptedResearcher(fail_once="How is profitability trending?")
    job = make_job(ticker="WDGT")
    worker = _worker(tmp_path, model)

    worker.run_once()
    with SessionLocal() as session:
        row = session.get(ResearchJob, job.id)
        assert row.status == ResearchJobStatus.QUEUED and "quota" in row.error_message
        assert _checkpoints(job.id) > 0  # the graph's progress survived the failed attempt
        session.execute(update(ResearchJob).where(ResearchJob.id == job.id).values(run_after=datetime.now(timezone.utc)))
        session.commit()

    worker.run_once()

    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED
    risks = [c for c in model.calls if "What are the main risks?" in c]
    profitability = [c for c in model.calls if "How is profitability trending?" in c]
    assert len(risks) == 2  # search + findings, once: the finished researcher was not re-run
    assert len(profitability) == 3  # failed call, then search + findings on the retry
    assert len(_runs(job.id, "planning")) == 1  # planning isn't repeated either
    assert _checkpoints(job.id) == 0


def test_cancel_during_research_stops_the_graph(make_job, tmp_path, monkeypatch):
    from backend.pipeline.base import JobContext

    job = make_job(ticker="WDGT")
    contexts: list[JobContext] = []
    checkpoint = JobContext.checkpoint

    def remember(self):
        contexts.append(self)
        return checkpoint(self)

    monkeypatch.setattr(JobContext, "checkpoint", remember)
    # The user presses Cancel while the first researcher is thinking; the heartbeat would set this event.
    model = ScriptedResearcher(on_call=lambda _task: contexts[-1].cancel_event.set())

    _worker(tmp_path, model).run_once()

    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.CANCELLED
        assert session.scalar(select(Report).where(Report.research_job_id == job.id)) is None
    assert not _runs(job.id, "drafting")


@pytest.mark.parametrize("pipeline", ["linear"])
def test_linear_pipeline_is_still_available_as_a_baseline(make_job, tmp_path, pipeline):
    job = make_job(ticker="WDGT")
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM)

    Worker(stages_factory=lambda: research_stages(services, agentic=False), retry_base_seconds=0).run_once()

    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED
    assert _runs(job.id, "analyzing") and not _runs(job.id, "planning")


def test_trace_endpoint_shows_plan_researchers_and_critic(make_job, tmp_path):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services.user import UserService

    with SessionLocal() as session:
        user = UserService().get_or_create_dev_user(session)
    job = make_job(user=user, ticker="WDGT")
    _worker(tmp_path, ScriptedResearcher()).run_once()
    client = TestClient(app)

    trace = client.get(f"/api/v1/research/{job.id}/trace").json()
    report = client.get(f"/api/v1/research/{job.id}/report").json()

    assert trace["mode"] == "agent"
    assert [q["question"] for q in trace["plan"]] == ["What are the main risks?", "How is profitability trending?"]
    assert {(r["task_id"], r["round"]) for r in trace["researchers"]} == {("q1", 0), ("q2", 0), ("r1g1", 1)}
    assert trace["researchers"][0]["tool_calls"][0]["tool"] == "search_filings"
    assert [(r["revision"], r["decision"]) for r in trace["rounds"]] == [(0, "revise"), (1, "finish")]
    assert trace["rounds"][0]["verdicts"]["unsupported"] == 2
    assert trace["totals"]["researchers"] == 3 and trace["totals"]["tool_calls"] == 3
    assert report["research"]["revisions"] == 1
    assert client.get(f"/api/v1/research/{uuid4()}/trace").status_code == 404


def test_a_revision_that_verifies_worse_is_undone(make_job, tmp_path):
    """Seen live: rate limits pushed the redraft onto a weak fallback model that dropped every quote."""
    from backend.pipeline import prompts

    class WorseSecondDraft(FakeLLM):
        drafts = 0

        def generate_json(self, *, prompt, schema, system, strong=False, temperature=0.2):
            result = super().generate_json(prompt=prompt, schema=schema, system=system, strong=strong, temperature=temperature)
            if schema is prompts.ClaimDraft:
                WorseSecondDraft.drafts += 1
                if WorseSecondDraft.drafts == 2:
                    for claim in result.value.claims:
                        claim.evidence, claim.metric_refs = [], []
            return result

    job = make_job(ticker="WDGT")
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=WorseSecondDraft,
                        agent_model_factory=scripted_agent_model(ScriptedResearcher()))
    Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()

    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED
        claims = {c.claim_text: c.verification_status for c in session.scalars(select(Claim).where(Claim.research_job_id == job.id))}
        report = session.scalar(select(Report).where(Report.research_job_id == job.id))
    critic = [r.extra_metadata for r in _runs(job.id, "critic")]
    assert [c["decision"] for c in critic] == ["revise", "restore", "finish"]
    assert "is restored" in critic[1]["reason"]
    assert _runs(job.id, "restore")[0].extra_metadata["restored_from"] == 0
    # The first draft's verdicts are back, evidence and all.
    assert claims["Widgetco sells widgets globally."] == "supported"
    assert claims["Operating margin was 25.0% in FY2024."] == "supported"
    assert report.full_report["research"]["restored_from"] == 0
    assert [r["restored"] for r in report.full_report["research"]["verify_rounds"]] == [False, False, True]


def test_a_researcher_that_never_uses_a_tool_contributes_nothing(make_job, tmp_path):
    """Seen live: on a retry, a model answered from memory and cited seven handles it had never been shown."""

    class Lazy(ScriptedResearcher):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult

            message = AIMessage(content="", tool_calls=[{"name": "Findings", "id": "call_lazy", "type": "tool_call", "args": {
                "answer": "From memory.", "notes": [{"text": "Something plausible.", "passages": ["P:0cbb01f9"], "metrics": []}],
                "gaps": [],
            }}])
            return ChatResult(generations=[ChatGeneration(message=message)])

    job = make_job(ticker="WDGT")
    _worker(tmp_path, Lazy()).run_once()

    researchers = [r.extra_metadata for r in _runs(job.id, "researching")]
    assert researchers and all(r["notes"] == 0 and r["dropped_handles"] == ["P:0cbb01f9"] for r in researchers)
    assert all("without consulting the filings" in r["gaps"][0] for r in researchers)
    # With no researcher evidence the draft falls back to one plain retrieval, so a report is still written.
    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED


def test_a_failed_researcher_still_records_its_task(make_job, tmp_path):
    job = make_job(ticker="WDGT")
    _worker(tmp_path, ScriptedResearcher(fail_once="How is profitability trending?")).run_once()

    failed = [r for r in _runs(job.id, "researching") if r.status == "failed"]
    assert failed and failed[0].extra_metadata["question"] == "How is profitability trending?"


def test_every_model_call_lands_in_the_cost_ledger_under_its_job_and_stage(make_job, tmp_path):
    """Researchers run in LangGraph's worker threads; the job/stage attribution must follow them there."""
    from backend.models import LlmCall

    job = make_job(ticker="WDGT")
    _worker(tmp_path, ScriptedResearcher(record_usage=True)).run_once()

    with SessionLocal() as session:
        calls = list(session.scalars(select(LlmCall).where(LlmCall.research_job_id == job.id)))
    researcher_calls = [c for c in calls if c.stage == "researching"]
    assert len(researcher_calls) == 2 * 3  # 3 researchers (2 planned + 1 revision) × (search turn + findings turn)
    assert all(c.source == "job" and c.cost_usd is not None for c in researcher_calls)
