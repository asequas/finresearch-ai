"""Cost tracker queries over the llm_calls ledger (ADR 0009)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.costs.budget import budget_status
from backend.costs.pricing import PRICING_CHECKED, PRICING_SOURCE
from backend.models.llm_call import LlmCall
from backend.models.research_job import ResearchJob, ResearchJobStatus
from backend.schemas.costs import BudgetOut, CostSummary, DaySpend, JobSpend, ModelSpend, Spend, StageSpend

ZERO = Decimal("0")


def _spend_columns():
    return (
        func.coalesce(func.sum(case((LlmCall.billable.is_(True), LlmCall.cost_usd), else_=0)), 0).label("billed"),
        func.coalesce(func.sum(LlmCall.cost_usd), 0).label("list_price"),
        func.count(LlmCall.id).label("calls"),
        func.coalesce(func.sum(LlmCall.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(LlmCall.cached_tokens), 0).label("cached_tokens"),
        func.coalesce(func.sum(LlmCall.output_tokens), 0).label("output_tokens"),
    )


def _spend(row) -> dict:
    return dict(
        billed=Decimal(row.billed), list_price=Decimal(row.list_price), calls=row.calls,
        input_tokens=row.input_tokens, cached_tokens=row.cached_tokens, output_tokens=row.output_tokens,
    )


def job_cost(session: Session, job_id) -> Decimal:
    """List-price cost of everything a job (and its chat) has spent so far."""
    return Decimal(session.scalar(
        select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(LlmCall.research_job_id == job_id)
    ) or 0)


class CostService:
    def summary(self, session: Session, *, days: int = 30, now: datetime | None = None) -> CostSummary:
        now = now or datetime.now(timezone.utc)
        start = datetime.combine((now - timedelta(days=days - 1)).date(), datetime.min.time(), tzinfo=timezone.utc)
        in_window = LlmCall.created_at >= start

        all_time = session.execute(select(*_spend_columns())).one()
        window = session.execute(select(*_spend_columns()).where(in_window)).one()

        day = cast(func.timezone("UTC", LlmCall.created_at), Date)
        by_day = {r.day: r for r in session.execute(select(day.label("day"), *_spend_columns()).where(in_window).group_by(day))}
        days_out = []
        for offset in range(days):
            d = start.date() + timedelta(days=offset)
            row = by_day.get(d)
            days_out.append(DaySpend(date=d, **(_spend(row) if row else dict(
                billed=ZERO, list_price=ZERO, calls=0, input_tokens=0, cached_tokens=0, output_tokens=0))))

        models = [
            ModelSpend(model=r.model, operation=r.operation, priced=r.priced == r.calls, **_spend(r))
            for r in session.execute(
                select(LlmCall.model, LlmCall.operation, func.count(LlmCall.cost_usd).label("priced"), *_spend_columns())
                .where(in_window)
                .group_by(LlmCall.model, LlmCall.operation).order_by(func.sum(LlmCall.cost_usd).desc().nulls_last())
            )
        ]
        stages = [
            StageSpend(source=r.source, stage=r.stage, **_spend(r))
            for r in session.execute(
                select(LlmCall.source, LlmCall.stage, *_spend_columns()).where(in_window)
                .group_by(LlmCall.source, LlmCall.stage).order_by(func.sum(LlmCall.cost_usd).desc().nulls_last())
            )
        ]
        jobs = [
            JobSpend(job_id=r.id, ticker=r.ticker, company=r.company, status=r.status, created_at=r.created_at, **_spend(r))
            for r in session.execute(
                select(ResearchJob.id, ResearchJob.ticker, ResearchJob.company, ResearchJob.status, ResearchJob.created_at,
                       *_spend_columns())
                .join(LlmCall, LlmCall.research_job_id == ResearchJob.id)
                .group_by(ResearchJob.id).order_by(ResearchJob.created_at.desc()).limit(25)
            )
        ]

        completed = session.execute(
            select(func.count(func.distinct(LlmCall.research_job_id)), func.coalesce(func.sum(LlmCall.cost_usd), 0))
            .join(ResearchJob, ResearchJob.id == LlmCall.research_job_id)
            .where(ResearchJob.status == ResearchJobStatus.COMPLETED, LlmCall.source == "job")
        ).one()
        per_job = (Decimal(completed[1]) / completed[0]).quantize(Decimal("0.00000001")) if completed[0] else None

        status = budget_status(session, now)
        return CostSummary(
            budget=BudgetOut(
                billing=settings.gemini_billing, daily_cap=status.daily_cap, monthly_cap=status.monthly_cap,
                today=status.today, month=status.month, day_resets_at=status.day_resets_at,
                month_resets_at=status.month_resets_at,
                blocked_reason=status.blocked_reason if settings.gemini_billing == "paid" else None,
            ),
            pricing_source=PRICING_SOURCE, pricing_checked=PRICING_CHECKED,
            all_time=Spend(**_spend(all_time)), window_days=days, window=Spend(**_spend(window)),
            per_job_average=per_job, days=days_out, models=models, stages=stages, jobs=jobs,
            unpriced_calls=session.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.cost_usd.is_(None))) or 0,
            estimated_calls=session.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.estimated.is_(True))) or 0,
            first_call_at=session.scalar(select(func.min(LlmCall.created_at))),
        )
