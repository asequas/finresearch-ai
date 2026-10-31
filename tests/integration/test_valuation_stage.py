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


def test_a_completed_job_carries_a_sourced_fair_value_and_citable_metrics(make_job, tmp_path):
    job, _ = _run(make_job, tmp_path)

    with SessionLocal() as session:
        assert session.get(ResearchJob, job.id).status == ResearchJobStatus.COMPLETED
        valuation = session.scalar(select(Valuation).where(Valuation.research_job_id == job.id))
        metrics = {m.metric_key: m for m in session.scalars(select(CalculatedMetric).where(
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key.startswith("val_")))}
        report = session.scalar(select(Report).where(Report.research_job_id == job.id))

    assert valuation.status == "valued" and valuation.method == "fair_value_blend" and valuation.industry == "Machinery"
    inputs = valuation.inputs
    assert inputs["risk_free_rate"] == "0.0450" and "Treasury" in inputs["sources"]["risk_free_rate"]
    # FY2024 free cash flow: 25B cash from operations + 0.5B × (1 − 20%) interest − 5B capex = 20.4B.
    assert Decimal(inputs["base_fcf"]) == Decimal(inputs["history"][-1]["fcf"]) == Decimal("20.4e9")
    assert abs(Decimal(inputs["initial_growth"]) - Decimal("0.10")) < Decimal("0.0001")  # revenue 100B → 121B over two years: 10% a year
    assert valuation.result["methods_used"] == ["dcf", "epv"]
    low, high = valuation.result["range_low"], valuation.result["range_high"]
    assert Decimal(low) <= valuation.value_per_share <= Decimal(high)
    assert set(metrics) == {"val_fair_value", "val_dcf_value", "val_epv_value", "val_cost_of_capital", "val_growth"}
    assert metrics["val_fair_value"].unit == "USD/share" and metrics["val_fair_value"].value == valuation.value_per_share
    assert any("Fair value blends a cash-flow DCF" in limitation for limitation in report.limitations)


def test_an_operating_loss_drops_earnings_power_and_keeps_the_cash_flow_method(make_job, tmp_path):
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
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key == "val_epv_value"))
    # Losses everywhere: no positive operating income, and FCF (25B − 5B) still positive → DCF alone applies.
    assert valuation.status == "valued" and valuation.result["methods_used"] == ["dcf"]
    assert any("earnings power value doesn't apply" in w for w in valuation.warnings)
    assert dcf_count == 0  # no val_epv_value metric
    assert not any(limitation.startswith("No fair value") for limitation in limitations)


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
            CalculatedMetric.research_job_id == job.id, CalculatedMetric.metric_key == "val_fair_value")) == 1
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
        session.execute(delete(CalculatedMetric).where(CalculatedMetric.metric_key.startswith("val_")))
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
