"""Full research pipeline against the real DB with a fake SEC transport and a fake LLM."""
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.core.database import SessionLocal
from backend.main import app
from backend.models import CalculatedMetric, Claim, Document, DocumentChunk, FinancialSnapshot, Report, ResearchJob
from backend.models.research_job import ResearchJobStatus
from backend.pipeline.research import Services, research_stages
from backend.worker.main import Worker
from tests.fakes import CIK, RESPONSES, FakeLLM, FakeSec, ScriptedResearcher, scripted_agent_model


@pytest.fixture
def run_job(make_job, tmp_path):
    def _run(ticker="WDGT", sec=None):
        job = make_job(ticker=ticker)
        services = Services(sec_factory=lambda: sec or FakeSec(tmp_path), llm_factory=FakeLLM,
                            agent_model_factory=scripted_agent_model(ScriptedResearcher()))
        Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()
        with SessionLocal() as session:
            return session.get(ResearchJob, job.id)
    return _run


def test_pipeline_produces_verified_report(run_job):
    job = run_job()

    assert job.status == ResearchJobStatus.COMPLETED, job.error_message
    with SessionLocal() as session:
        snapshots = session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.research_job_id == job.id)).all()
        assert [s.period for s in sorted(snapshots, key=lambda s: s.fiscal_year)] == ["FY2022", "FY2023", "FY2024"]
        fy24 = next(s for s in snapshots if s.fiscal_year == 2024)
        assert fy24.revenue == Decimal("121000000000.0000")
        assert fy24.provenance["revenue"]["concept"] == "us-gaap:Revenues"

        margin = session.scalar(select(CalculatedMetric).where(
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key == "operating_margin",
            CalculatedMetric.period == "FY2024"))
        assert margin.value == Decimal("0.25")

        assert session.scalar(select(func.count()).select_from(DocumentChunk)) > 0
        document = session.scalar(select(Document))
        assert document.indexed_at is not None and document.form_type == "10-K"

        claims = {c.claim_text: c for c in session.scalars(select(Claim).where(Claim.research_job_id == job.id))}
        assert claims["Widgetco sells widgets globally."].verification_status == "supported"
        assert claims["Operating margin was 25.0% in FY2024."].verification_status == "supported"
        assert claims["Operating margin was 99.0% in FY2024."].verification_status == "unsupported"
        assert claims["Steel shortages are a risk."].verification_status == "unsupported"

        report = session.scalar(select(Report).where(Report.research_job_id == job.id))
        assert report.full_report["headline"].startswith("Widgetco")
        assert report.data_as_of.isoformat() == "2024-09-30"
        assert any("doesn't compare its fair value with the share price" in limitation for limitation in report.limitations)
        assert len(report.full_report["key_points"][0]["claim_ids"]) == 2


def test_report_endpoint_returns_evidence_and_calculations(run_job):
    job = run_job()
    # Reassign the job to the dev user so the API (dev identity) can read it.
    from backend.services.user import UserService
    with SessionLocal() as session:
        user = UserService().get_or_create_dev_user(session)
        session.get(ResearchJob, job.id).user_id = user.id
        session.commit()

    response = TestClient(app).get(f"/api/v1/research/{job.id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["company"]["cik"] == CIK
    assert body["headline"].startswith("Widgetco")
    fact = next(c for c in body["claims"] if c["text"] == "Widgetco sells widgets globally.")
    assert fact["evidence"][0]["quote_verified"] is True
    assert fact["evidence"][0]["document"]["form"] == "10-K"
    calc = next(c for c in body["claims"] if c["text"] == "Operating margin was 25.0% in FY2024.")
    assert calc["metrics"][0]["formula"] == "operating_income / revenue"
    assert calc["metrics"][0]["inputs"]["revenue"]["value"].startswith("121000000000")
    assert {row["period"] for row in body["financials"]} == {"FY2022", "FY2023", "FY2024"}
    assert body["verification_summary"]["supported"] == 2


def test_financial_sector_company_fails_permanently(run_job, tmp_path):
    responses = json.loads(json.dumps(RESPONSES))
    responses[f"https://data.sec.gov/submissions/CIK{CIK}.json"]["sic"] = "6021"
    responses[f"https://data.sec.gov/submissions/CIK{CIK}.json"]["sicDescription"] = "National Commercial Banks"

    job = run_job(sec=FakeSec(tmp_path, responses))

    assert job.status == ResearchJobStatus.FAILED
    assert "financial-sector" in job.error_message
    assert job.attempts == 1


def test_unknown_ticker_fails_with_readable_reason(run_job):
    job = run_job(ticker="NOPE")

    assert job.status == ResearchJobStatus.FAILED
    assert job.error_message == "Ticker NOPE was not found in SEC EDGAR's company list."


def test_rerunning_stages_is_idempotent(run_job, tmp_path):
    job = run_job()
    with SessionLocal() as session:
        before = {
            "snapshots": session.scalar(select(func.count()).select_from(FinancialSnapshot)),
            "metrics": session.scalar(select(func.count()).select_from(CalculatedMetric)),
            "claims": session.scalar(select(func.count()).select_from(Claim)),
            "chunks": session.scalar(select(func.count()).select_from(DocumentChunk)),
            "reports": session.scalar(select(func.count()).select_from(Report)),
        }

    # A user retry re-runs nothing that was checkpointed; force a full re-run by clearing checkpoints.
    from sqlalchemy import delete
    from backend.models import AgentRun
    with SessionLocal() as session:
        session.execute(delete(AgentRun).where(AgentRun.research_job_id == job.id))
        job_row = session.get(ResearchJob, job.id)
        job_row.status = ResearchJobStatus.QUEUED
        session.commit()
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM,
                        agent_model_factory=scripted_agent_model(ScriptedResearcher()))
    Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()

    with SessionLocal() as session:
        after = {
            "snapshots": session.scalar(select(func.count()).select_from(FinancialSnapshot)),
            "metrics": session.scalar(select(func.count()).select_from(CalculatedMetric)),
            "claims": session.scalar(select(func.count()).select_from(Claim)),
            "chunks": session.scalar(select(func.count()).select_from(DocumentChunk)),
            "reports": session.scalar(select(func.count()).select_from(Report)),
        }
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED
    assert after == before


def test_evaluation_metrics_and_label_scoring(run_job):
    from backend.evals.citations import auto_metrics, export_for_labelling, score_labels

    job = run_job()
    with SessionLocal() as session:
        metrics = auto_metrics(session, job.id)
        items = export_for_labelling(session, job.id)

    assert metrics.claims == 4
    assert metrics.material_claims == 4
    assert metrics.citation_coverage == 0.75  # the fabricated quote leaves one fact uncovered
    assert metrics.quote_verification_rate == 0.5
    assert metrics.numeric_consistency == 0.5  # the 99.0% claim fails the numeric check
    assert len(items) == 4 and all(i["label"] is None for i in items)

    for item in items:
        item["label"] = "correct" if item["system_verdict"] == "supported" else "incorrect"
    score = score_labels(items)
    assert score.labelled == 4
    assert score.citation_correctness == 0.5
    assert score.meets_target is False
    assert score.system_supported_precision == 1.0


def test_company_workspace_endpoint(run_job):
    job = run_job()
    from backend.services.user import UserService
    with SessionLocal() as session:
        user = UserService().get_or_create_dev_user(session)
        session.get(ResearchJob, job.id).user_id = user.id
        session.commit()
    client = TestClient(app)

    body = client.get("/api/v1/companies/wdgt").json()

    assert body["company"]["ticker"] == "WDGT"
    assert body["latest_report_job_id"] == str(job.id)
    assert [f["period"] for f in body["financials"]] == ["FY2022", "FY2023", "FY2024"]
    assert any(m["key"] == "operating_margin" for m in body["metrics"])
    assert body["jobs"][0]["has_report"] is True
    assert client.get("/api/v1/companies/NOPE").status_code == 404

    meta = client.get("/api/v1/meta").json()
    assert {t["stage"] for t in meta["stage_timings"]} >= {"resolving_company", "synthesizing"}
    assert meta["reranker"] == "none"
