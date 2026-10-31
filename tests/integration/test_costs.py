"""The cost ledger and budget caps (ADR 0009)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.costs.budget import BudgetExceeded, budget_status, ensure_budget
from backend.costs.ledger import record_call, usage_scope
from backend.main import app
from backend.models import LlmCall


def _calls():
    with SessionLocal() as session:
        return list(session.scalars(select(LlmCall).order_by(LlmCall.created_at)))


def test_a_call_is_priced_attributed_and_marked_free_on_the_free_tier(make_job, monkeypatch):
    monkeypatch.setattr(settings, "gemini_billing", "free")
    job = make_job()

    with usage_scope(job_id=job.id, source="job", stage="drafting"):
        record_call(model="models/gemini-3.5-flash-lite", operation="generate", input_tokens=20_000, cached_tokens=0,
                    output_tokens=4_000, thinking_tokens=1_000)

    [call] = _calls()
    assert (call.research_job_id, call.source, call.stage, call.model) == (job.id, "job", "drafting", "gemini-3.5-flash-lite")
    assert call.cost_usd == Decimal("0.01600000")  # 20k × $0.30 + 4k × $2.50 per 1M
    assert call.billable is False


def test_budget_blocks_only_billed_spend_and_says_when_it_resets(monkeypatch):
    monkeypatch.setattr(settings, "gemini_billing", "paid")
    monkeypatch.setattr(settings, "budget_daily_usd", Decimal("0.05"))
    record_call(model="gemini-3.6-flash", operation="generate", input_tokens=40_000, output_tokens=8_000)  # $0.06

    with SessionLocal() as session:
        status = budget_status(session)
    assert status.today == Decimal("0.06000000")
    assert "Today's AI budget of $0.05 is spent" in status.blocked_reason
    with pytest.raises(BudgetExceeded):
        ensure_budget()

    monkeypatch.setattr(settings, "gemini_billing", "free")
    ensure_budget()  # free tier never blocks


def test_spent_budget_refuses_new_research_with_429(monkeypatch):
    monkeypatch.setattr(settings, "gemini_billing", "paid")
    monkeypatch.setattr(settings, "budget_daily_usd", Decimal("0.01"))
    record_call(model="gemini-3.6-flash", operation="generate", input_tokens=40_000, output_tokens=8_000)

    response = TestClient(app).post("/api/v1/research", json={"query": "How is Apple doing?", "company": "Apple", "ticker": "AAPL"})

    assert response.status_code == 429 and "budget" in response.json()["detail"]


def test_monthly_cap_counts_the_whole_month(monkeypatch):
    monkeypatch.setattr(settings, "gemini_billing", "paid")
    monkeypatch.setattr(settings, "budget_monthly_usd", Decimal("0.10"))
    record_call(model="gemini-3.6-flash", operation="generate", input_tokens=100_000, output_tokens=20_000)  # $0.15
    with SessionLocal() as session:
        call = session.scalar(select(LlmCall))
        call.created_at = datetime.now(timezone.utc).replace(day=1, hour=0, minute=1)
        session.commit()
        status = budget_status(session)
    assert status.month == Decimal("0.15000000")
    assert status.blocked_reason and "month" in status.blocked_reason
