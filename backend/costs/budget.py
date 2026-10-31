"""Spending caps (ADR 0009): counted from billed ledger rows, checked before every model call and every submit."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.pipeline.base import PermanentError


class BudgetExceeded(PermanentError):
    """The daily or monthly cap is spent. Jobs stop with this message; a retry after the reset resumes them."""


@dataclass(frozen=True)
class BudgetStatus:
    daily_cap: Decimal
    monthly_cap: Decimal
    today: Decimal
    month: Decimal
    day_resets_at: datetime
    month_resets_at: datetime

    @property
    def blocked_reason(self) -> str | None:
        if self.today >= self.daily_cap:
            return (f"Today's AI budget of ${self.daily_cap:.2f} is spent (${self.today:.2f}). "
                    f"It resets at {self.day_resets_at:%H:%M} UTC.")
        if self.month >= self.monthly_cap:
            return (f"This month's AI budget of ${self.monthly_cap:.2f} is spent (${self.month:.2f}). "
                    f"It resets on {self.month_resets_at:%b %d}.")
        return None


def period_starts(now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """Start of today and this month in UTC, and when each resets."""
    day = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    month = day.replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    return day, month, day + timedelta(days=1), next_month


def budget_status(session: Session, now: datetime | None = None) -> BudgetStatus:
    from backend.models.llm_call import LlmCall

    now = now or datetime.now(timezone.utc)
    day, month, day_reset, month_reset = period_starts(now)

    def billed_since(start: datetime) -> Decimal:
        total = session.scalar(
            select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(LlmCall.billable.is_(True), LlmCall.created_at >= start)
        )
        return Decimal(total or 0)

    return BudgetStatus(
        daily_cap=settings.budget_daily_usd, monthly_cap=settings.budget_monthly_usd,
        today=billed_since(day), month=billed_since(month), day_resets_at=day_reset, month_resets_at=month_reset,
    )


def ensure_budget(session_factory=None) -> None:
    """Raise BudgetExceeded when a cap is spent. Free-tier calls are never billed, so they never block."""
    if settings.gemini_billing != "paid":
        return
    from backend.core.database import SessionLocal

    with (session_factory or SessionLocal)() as session:
        reason = budget_status(session).blocked_reason
    if reason:
        raise BudgetExceeded(reason)
