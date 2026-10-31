"""Valuation API: the stored fair value, set against a delayed or typed price, and what-ifs (ADR 0012)."""
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.api.routes.research import get_valuation_service
from backend.core.database import SessionLocal
from backend.main import app
from backend.pipeline.research import Services, research_stages
from backend.services.user import UserService
from backend.services.valuation import ValuationService
from backend.valuation.price import MarketPrice
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


@pytest.fixture
def quote():
    """Pretend the delayed quote is available at a chosen price."""
    price = {"value": None}

    def fetch(ticker):
        return MarketPrice(price["value"], datetime(2026, 10, 30, 15, 59), "Cboe delayed quote (test)") if price["value"] else None

    app.dependency_overrides[get_valuation_service] = lambda: ValuationService(price_fetcher=fetch)
    yield price
    app.dependency_overrides.pop(get_valuation_service, None)


def test_fair_value_with_both_methods_and_every_sourced_assumption(valued_job):
    body = TestClient(app).get(f"/api/v1/research/{valued_job.id}/valuation").json()

    assert body["status"] == "valued" and body["methods_used"] == ["dcf", "epv"]
    fair = Decimal(body["fair_value"])
    assert Decimal(body["range_low"]) <= fair <= Decimal(body["range_high"])
    mean = (Decimal(body["dcf"]["value_per_share"]) + Decimal(body["epv"]["value_per_share"])) / 2
    assert abs(fair - mean) <= Decimal("0.01")
    assumptions = {a["key"]: a for a in body["assumptions"]}
    assert assumptions["initial_growth"]["editable"] and not assumptions["risk_free_rate"]["editable"]
    assert len(body["fcf_history"]) == 1 and len(body["dcf"]["projection"]) == 10
    assert body["market_price"] is None and body["price_check"] is None  # no quote source in tests


def test_the_delayed_quote_is_checked_against_the_range_automatically(valued_job, quote):
    client = TestClient(app)
    fair = Decimal(client.get(f"/api/v1/research/{valued_job.id}/valuation").json()["fair_value"])

    quote["value"] = (fair / 3).quantize(Decimal("0.01"))
    cheap = client.get(f"/api/v1/research/{valued_job.id}/valuation").json()
    quote["value"] = (fair * 3).quantize(Decimal("0.01"))
    dear = client.get(f"/api/v1/research/{valued_job.id}/valuation").json()

    assert cheap["market_price"]["source"].startswith("Cboe") and cheap["price_check"]["position"] == "below_range"
    assert "undervalued" in cheap["price_check"]["explanation"]
    assert dear["price_check"]["position"] == "above_range" and "overvalued" in dear["price_check"]["explanation"]
    growth = Decimal(next(a["value"] for a in dear["assumptions"] if a["key"] == "initial_growth"))
    assert Decimal(dear["price_check"]["implied_growth"]) > growth


def test_a_typed_price_overrides_the_quote_and_changes_no_assumption(valued_job, quote):
    quote["value"] = Decimal("1.00")
    body = TestClient(app).post(f"/api/v1/research/{valued_job.id}/valuation/what-if", json={"market_price": "250"}).json()

    assert body["market_price"] == {"price": "250", "as_of": None, "source": "entered by you"}
    assert body["what_if"] is False and body["overridden"] == []


def test_the_price_check_compares_with_the_record_not_a_what_if_growth(valued_job):
    body = TestClient(app).post(f"/api/v1/research/{valued_job.id}/valuation/what-if",
                                json={"initial_growth": "0.3", "market_price": "1500"}).json()

    assert "the revenue record suggests 10.0%" in body["price_check"]["explanation"]


def test_what_if_recomputes_from_stored_inputs_and_saves_nothing(valued_job):
    client = TestClient(app)
    base = client.get(f"/api/v1/research/{valued_job.id}/valuation").json()

    lower = client.post(f"/api/v1/research/{valued_job.id}/valuation/what-if",
                        json={"initial_growth": "0.01", "equity_risk_premium": "0.06"}).json()

    assert lower["what_if"] is True and lower["overridden"] == ["equity_risk_premium", "initial_growth"]
    assert Decimal(lower["fair_value"]) < Decimal(base["fair_value"])
    assert client.get(f"/api/v1/research/{valued_job.id}/valuation").json() == base


def test_what_if_bounds_and_model_errors(valued_job):
    client = TestClient(app)
    url = f"/api/v1/research/{valued_job.id}/valuation/what-if"
    assert client.post(url, json={"initial_growth": "0.9"}).status_code == 422
    assert client.post(url, json={"market_price": "0"}).status_code == 422
    broken = client.post(url, json={"stable_growth": "0.05"})  # above the 4.50% risk-free rate
    assert broken.status_code == 400 and "risk-free rate" in broken.json()["detail"]


def test_valuations_are_private(valued_job, make_job):
    from uuid import uuid4

    client = TestClient(app)
    assert client.get(f"/api/v1/research/{make_job().id}/valuation").status_code == 404
    assert client.get(f"/api/v1/research/{uuid4()}/valuation").status_code == 404
    assert client.get("/api/v1/companies/WDGT").json()["latest_valuation"]["job_id"] == str(valued_job.id)
