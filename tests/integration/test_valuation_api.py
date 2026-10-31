"""Valuation API: read the stored DCF, run what-ifs on its stored inputs (ADR 0010)."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.core.database import SessionLocal
from backend.main import app
from backend.pipeline.research import Services, research_stages
from backend.services.user import UserService
from backend.worker.main import Worker
from tests.fakes import FakeLLM, FakeSec, ScriptedResearcher, scripted_agent_model


@pytest.fixture
def valued_job(make_job, tmp_path):
    with SessionLocal() as session:
        user = UserService().get_or_create_dev_user(session)
    job = make_job(user=user, ticker="WDGT")
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM,
                        agent_model_factory=scripted_agent_model(ScriptedResearcher()))
    Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()
    return job


def test_valuation_shows_value_range_and_every_sourced_assumption(valued_job):
    body = TestClient(app).get(f"/api/v1/research/{valued_job.id}/valuation").json()

    assert body["status"] == "valued" and body["industry"] == "Machinery" and body["base_year"] == 2024
    value = Decimal(body["value_per_share"])
    assert Decimal(body["range_low"]) < value < Decimal(body["range_high"])
    assumptions = {a["key"]: a for a in body["assumptions"]}
    assert assumptions["risk_free_rate"]["editable"] is False and "Treasury" in assumptions["risk_free_rate"]["source"]
    assert assumptions["high_growth"]["editable"] is True
    assert assumptions["stable_return_on_capital"]["source"].startswith("midway between")
    assert len(body["projection"]) == 15 and body["bridge"]["value_per_share"] == body["value_per_share"]
    assert body["what_if"] is False


def test_what_if_recomputes_from_stored_inputs_and_saves_nothing(valued_job):
    client = TestClient(app)
    base = client.get(f"/api/v1/research/{valued_job.id}/valuation").json()

    lower = client.post(f"/api/v1/research/{valued_job.id}/valuation/what-if",
                        json={"high_growth": "0.01", "equity_risk_premium": "0.06"}).json()
    again = client.get(f"/api/v1/research/{valued_job.id}/valuation").json()

    assert lower["what_if"] is True and lower["overridden"] == ["equity_risk_premium", "high_growth"]
    assert Decimal(lower["value_per_share"]) < Decimal(base["value_per_share"])
    assert {a["key"]: a["source"] for a in lower["assumptions"]}["high_growth"] == "what-if (user override)"
    assert again == base  # the stored valuation is unchanged


def test_what_if_rejects_out_of_range_and_model_breaking_assumptions(valued_job):
    client = TestClient(app)
    url = f"/api/v1/research/{valued_job.id}/valuation/what-if"

    assert client.post(url, json={"high_growth": "0.9"}).status_code == 422  # outside the allowed range
    broken = client.post(url, json={"stable_growth": "0.05"})  # above the 4.50% risk-free rate
    assert broken.status_code == 400 and "risk-free rate" in broken.json()["detail"]


def test_valuations_are_private_and_missing_ones_are_404(valued_job, make_job):
    from uuid import uuid4

    client = TestClient(app)
    other = make_job()  # someone else's job

    assert client.get(f"/api/v1/research/{other.id}/valuation").status_code == 404
    assert client.get(f"/api/v1/research/{uuid4()}/valuation").status_code == 404
    company = client.get("/api/v1/companies/WDGT").json()
    assert company["latest_valuation"]["job_id"] == str(valued_job.id)


def test_price_check_places_a_typed_price_against_the_range_and_solves_implied_growth(valued_job):
    client = TestClient(app)
    url = f"/api/v1/research/{valued_job.id}/valuation/what-if"
    base = client.get(f"/api/v1/research/{valued_job.id}/valuation").json()
    value = Decimal(base["value_per_share"])

    cheap = client.post(url, json={"market_price": str(value / 2)}).json()["price_check"]
    dear = client.post(url, json={"market_price": str(value * 2)}).json()
    fair = client.post(url, json={"market_price": str(value)}).json()["price_check"]

    assert cheap["position"] == "below_range" and Decimal(cheap["gap"]) > 0 and "undervalued" in cheap["explanation"]
    assert dear["price_check"]["position"] == "above_range" and "overvalued" in dear["price_check"]["explanation"]
    assert dear["what_if"] is False and dear["overridden"] == []  # a price alone changes no assumption
    assert fair["position"] == "within_range"
    # At the model's own value, the implied growth is the model's growth.
    model_growth = Decimal(next(a["value"] for a in base["assumptions"] if a["key"] == "high_growth"))
    assert abs(Decimal(fair["implied_high_growth"]) - model_growth) < Decimal("0.0005")
    assert Decimal(dear["price_check"]["implied_high_growth"]) > model_growth
    assert client.post(url, json={"market_price": "0"}).status_code == 422
