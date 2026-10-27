"""Full research pipeline against the real DB with a fake SEC transport and a fake LLM."""
import hashlib
import json
import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.core.database import SessionLocal
from backend.llm.client import LLMResult, normalise
from backend.main import app
from backend.models import CalculatedMetric, Claim, Document, DocumentChunk, FinancialSnapshot, Report, ResearchJob
from backend.models.research_job import ResearchJobStatus
from backend.pipeline import prompts
from backend.pipeline.research import Services, research_stages
from backend.sources.sec import SecClient
from backend.worker.main import Worker

CIK = "0000999999"


def _flow(val, year):
    return {"val": val, "start": f"{year - 1}-10-01", "end": f"{year}-09-30", "filed": f"{year}-11-01", "form": "10-K", "accn": f"0000999999-{year % 100}-000001"}


def _instant(val, year):
    return {"val": val, "end": f"{year}-09-30", "filed": f"{year}-11-01", "form": "10-K", "accn": f"0000999999-{year % 100}-000001"}


COMPANY_FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": [_flow(100e9, 2022), _flow(110e9, 2023), _flow(121e9, 2024)]}},
            "GrossProfit": {"units": {"USD": [_flow(40e9, 2022), _flow(45e9, 2023), _flow(50e9, 2024)]}},
            "OperatingIncomeLoss": {"units": {"USD": [_flow(20e9, 2022), _flow(24e9, 2023), _flow(30.25e9, 2024)]}},
            "NetIncomeLoss": {"units": {"USD": [_flow(15e9, 2022), _flow(18e9, 2023), _flow(22e9, 2024)]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_flow(25e9, 2024)]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [_flow(5e9, 2024)]}},
            "StockholdersEquity": {"units": {"USD": [_instant(60e9, 2023), _instant(70e9, 2024)]}},
        }
    }
}

FILING_HTML = (
    "<html><body><p>Item 1. Business</p><p>Item 1A. Risk Factors</p><p>Item 7. Management's Discussion and Analysis</p>"
    "<p>Item 1. Business</p>"
    + "<p>Widgetco designs industrial widgets and sells them to manufacturers in over forty countries.</p>" * 12
    + "<p>Item 1A. Risk Factors</p>"
    + "<p>A shortage of specialty steel could interrupt widget production and reduce margins.</p>" * 12
    + "<p>Item 7. Management's Discussion and Analysis of Financial Condition</p>"
    + "<p>Net sales grew due to strong demand for premium widgets in Europe.</p>" * 12
    + "<p>Item 8. Financial Statements</p></body></html>"
)

RESPONSES = {
    "https://www.sec.gov/files/company_tickers.json": {"0": {"cik_str": 999999, "ticker": "WDGT", "title": "Widgetco"}},
    f"https://data.sec.gov/submissions/CIK{CIK}.json": {
        "name": "Widgetco Inc.", "sic": "3560", "sicDescription": "General Industrial Machinery", "fiscalYearEnd": "0930",
        "exchanges": ["NYSE"],
        "filings": {"recent": {
            "form": ["10-K"], "accessionNumber": ["0000999999-24-000001"], "filingDate": ["2024-11-01"],
            "reportDate": ["2024-09-30"], "primaryDocument": ["wdgt-10k.htm"], "primaryDocDescription": ["10-K"],
        }},
    },
    f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json": COMPANY_FACTS,
}


class FakeSec(SecClient):
    def __init__(self, tmp_path, responses=RESPONSES):
        super().__init__("FinResearch tests test@example.com", tmp_path)
        self.responses = responses

    def fetch(self, url, *, max_age_seconds):
        if url.endswith("wdgt-10k.htm"):
            return FILING_HTML.encode()
        if url in self.responses:
            return json.dumps(self.responses[url]).encode()
        return None


class FakeLLM:
    """Follows the prompt contract: quotes verbatim from excerpts, cites metric ids, never invents numbers."""

    fast_model = "fake-fast"
    strong_model = "fake-strong"

    def embed(self, texts, *, task):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(" ".join(sorted(set(text.lower().split()))).encode()).digest()
            vectors.append(normalise([digest[i % 32] - 128.0 for i in range(768)]))
        return vectors

    def generate_json(self, *, prompt, schema, system, strong=False, temperature=0.2):
        if schema is prompts.ResearchPlan:
            value = schema(sub_questions=["What are the main risks?", "How is profitability trending?"])
        elif schema is prompts.ClaimDraft:
            excerpts = dict(re.findall(r"\[(E\d+)\] \([^)]*\)\n([^\n]+)", prompt))
            metrics = dict(re.findall(r"(M\d+): Operating margin FY2024 = ([\d.]+%)", prompt))
            first_id, first_text = next(iter(excerpts.items()))
            metric_id, shown = next(iter(metrics.items()))
            value = schema(claims=[
                prompts.DraftClaim(section="business", claim_type="fact", text="Widgetco sells widgets globally.",
                                   evidence=[prompts.EvidenceRef(excerpt_id=first_id, quote=first_text)], importance=3),
                prompts.DraftClaim(section="profitability", claim_type="calculation",
                                   text=f"Operating margin was {shown} in FY2024.", metric_refs=[metric_id], importance=3),
                prompts.DraftClaim(section="profitability", claim_type="calculation",
                                   text="Operating margin was 99.0% in FY2024.", metric_refs=[metric_id], importance=1),
                prompts.DraftClaim(section="risks", claim_type="fact", text="Steel shortages are a risk.",
                                   evidence=[prompts.EvidenceRef(excerpt_id=first_id, quote="this sentence is not in the filing at all")],
                                   importance=2),
            ])
        elif schema is prompts.Judgements:
            value = schema(judgements=[prompts.Judgement(claim_id=cid, verdict="supported", note="Quote matches.")
                                       for cid in re.findall(r"^(C\d+) ", prompt, re.MULTILINE)])
        elif schema is prompts.ReportDraft:
            value = schema(
                headline="Widgetco: growing, profitable, steel-exposed",
                direct_answer="Revenue and margins have grown steadily.",
                executive_summary="Widgetco grew revenue with expanding margins.",
                key_points=[prompts.KeyPoint(text="Margins expanded.", claim_ids=["C1", "C2"])],
                investment_thesis="Premium demand supports margins.",
                scenarios=[prompts.Scenario(name=n, summary=n, assumptions=[prompts.Assumption(driver="growth", assumption="10%", basis="M1")]) for n in ("bull", "base", "bear")],
                risks=[prompts.Risk(title="Steel", description="Input shortages", severity="high", claim_ids=["C1"])],
                open_questions=["How concentrated are customers?"],
            )
        else:
            raise AssertionError(schema)
        return LLMResult(value=value, model=self.strong_model if strong else self.fast_model, input_tokens=100, output_tokens=50)


@pytest.fixture
def run_job(make_job, tmp_path):
    def _run(ticker="WDGT", sec=None):
        job = make_job(ticker=ticker)
        services = Services(sec_factory=lambda: sec or FakeSec(tmp_path), llm_factory=FakeLLM)
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
        assert any("price data" in limitation for limitation in report.limitations)
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
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM)
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
