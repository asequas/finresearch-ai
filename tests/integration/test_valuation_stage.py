"""The deterministic DCF stage inside the research pipeline (ADR 0010)."""
import json
from decimal import Decimal

from sqlalchemy import func, select

from backend.core.database import SessionLocal
from backend.models import CalculatedMetric, LlmCall, Report, ResearchJob, Valuation
from backend.models.research_job import ResearchJobStatus
from backend.pipeline.research import Services, research_stages
from backend.worker.main import Worker
from tests.fakes import CIK, RESPONSES, FakeLLM, FakeSec, ScriptedResearcher, scripted_agent_model


def _run(make_job, tmp_path, responses=RESPONSES):
    job = make_job(ticker="WDGT")
    services = Services(sec_factory=lambda: FakeSec(tmp_path, responses), llm_factory=FakeLLM,
                        agent_model_factory=scripted_agent_model(ScriptedResearcher()))
    Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()
    return job, services


def test_a_completed_job_carries_a_sourced_dcf_valuation_and_citable_metrics(make_job, tmp_path):
    job, _ = _run(make_job, tmp_path)

    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED
        valuation = session.scalar(select(Valuation).where(Valuation.research_job_id == job.id))
        metrics = {m.metric_key: m for m in session.scalars(select(CalculatedMetric).where(
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key.startswith("dcf_")))}
        report = session.scalar(select(Report).where(Report.research_job_id == job.id))

    assert valuation.status == "valued" and valuation.value_per_share > 0
    assert valuation.industry == "Machinery"  # SIC 3560
    inputs = valuation.inputs
    assert inputs["risk_free_rate"] == "0.0450" and "Treasury" in inputs["sources"]["risk_free_rate"]
    assert inputs["base_ebit"] == "30250000000.0000" and inputs["effective_tax_rate"] == "0.2"  # 6B tax / 30B pre-tax
    assert "Machinery" in inputs["sources"]["unlevered_beta"] and inputs["sources"]["industry"] == "Machinery"
    assert inputs["lease_liabilities"] == "0"  # already inside operating income
    # ROC ~39% vs ~8% cost of capital: a lasting advantage, so 10 high-growth years + 5 transition (ADR 0011).
    assert inputs["high_growth_years"] == 10 and inputs["sources"]["high_growth_years"].startswith("10: return on capital")
    assert len(valuation.result["projection"]) == 15 and valuation.result["sensitivity"]["value_per_share"]
    assert inputs["sources"]["stable_return_on_capital"].startswith("midway between")
    assert set(metrics) == {"dcf_value_per_share", "dcf_equity_value", "dcf_operating_value", "dcf_cost_of_capital",
                            "dcf_high_growth", "dcf_stable_growth", "dcf_terminal_share"}
    assert metrics["dcf_value_per_share"].unit == "USD/share"
    assert metrics["dcf_value_per_share"].value == valuation.value_per_share
    assert any("DCF uses industry-average beta" in limitation for limitation in report.limitations)


def test_an_operating_loss_is_recorded_as_skipped_with_its_reason(make_job, tmp_path):
    responses = json.loads(json.dumps(RESPONSES))
    facts = responses[f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"]["facts"]["us-gaap"]
    for fact in facts["OperatingIncomeLoss"]["units"]["USD"]:
        fact["val"] = -abs(fact["val"])

    job, _ = _run(make_job, tmp_path, responses)

    from backend.pipeline.research import build_limitations

    with SessionLocal() as session:
        valuation = session.scalar(select(Valuation).where(Valuation.research_job_id == job.id))
        limitations = build_limitations(session, job.id)
        dcf_count = session.scalar(select(func.count()).select_from(CalculatedMetric).where(
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key.startswith("dcf_")))
    assert valuation.status == "skipped" and "Operating income" in valuation.skip_reason
    assert dcf_count == 0
    assert any(limitation.startswith("No DCF value: Operating income") for limitation in limitations)


def test_revaluing_replaces_rather_than_duplicates_and_spends_nothing(make_job, tmp_path):
    from sqlalchemy import delete

    from backend.models import AgentRun

    job, services = _run(make_job, tmp_path)
    with SessionLocal() as session:  # force every stage to run again, as a full user re-run would
        session.execute(delete(AgentRun).where(AgentRun.research_job_id == job.id))
        session.get(ResearchJob, job.id).status = ResearchJobStatus.QUEUED
        session.commit()
    Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()

    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Valuation).where(Valuation.research_job_id == job.id)) == 1
        assert session.scalar(select(func.count()).select_from(CalculatedMetric).where(
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key == "dcf_value_per_share")) == 1
        assert session.scalar(select(func.count()).select_from(LlmCall)) == 0  # the fakes never reach a model


def test_backfill_values_old_jobs_filling_only_missing_facts(make_job, tmp_path):
    from datetime import date

    from sqlalchemy import delete

    from backend.models import FinancialSnapshot
    from backend.valuation.backfill import backfill
    from backend.valuation.market import RiskFreeRate

    job, _ = _run(make_job, tmp_path)
    with SessionLocal() as session:  # make it look like a job from before the DCF existed
        session.execute(delete(Valuation).where(Valuation.research_job_id == job.id))
        session.execute(delete(CalculatedMetric).where(CalculatedMetric.metric_key.startswith("dcf_")))
        for snapshot in session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.research_job_id == job.id)):
            snapshot.depreciation_amortization = snapshot.income_tax_expense = snapshot.pretax_income = None
            snapshot.revenue = snapshot.revenue + 1  # a stored value that must not be overwritten
        session.commit()

    lines = backfill(["wdgt"], sec=FakeSec(tmp_path),
                     risk_free=RiskFreeRate(Decimal("0.0450"), date(2026, 10, 30), "test"))

    with SessionLocal() as session:
        valuation = session.scalar(select(Valuation).where(Valuation.research_job_id == job.id))
        fy24 = session.scalar(select(FinancialSnapshot).where(
            FinancialSnapshot.research_job_id == job.id, FinancialSnapshot.fiscal_year == 2024))
    assert len(lines) == 1 and "a share" in lines[0]
    assert valuation.status == "valued"
    assert fy24.depreciation_amortization == Decimal("3000000000.0000")
    assert fy24.provenance["depreciation_amortization"]["concept"] == "us-gaap:DepreciationAndAmortization"
    assert fy24.revenue == Decimal("121000000001.0000")  # untouched
    assert backfill(["WDGT"], sec=FakeSec(tmp_path), risk_free=RiskFreeRate(Decimal("0.045"), date(2026, 10, 30), "t")) == []
