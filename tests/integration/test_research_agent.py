"""The LangGraph research agent inside the durable queue: routing, bounds, resume and cancellation."""
from datetime import datetime, timezone

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
