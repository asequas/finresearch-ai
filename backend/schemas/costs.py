"""API shapes for the cost tracker (ADR 0009). Money is Decimal end to end; the client formats it."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class Spend(BaseModel):
    billed: Decimal  # what Google charged (paid-tier calls only)
    list_price: Decimal  # what the same calls cost at paid-tier prices
    calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int


class BudgetOut(BaseModel):
    billing: str  # "free" or "paid"
    daily_cap: Decimal
    monthly_cap: Decimal
    today: Decimal
    month: Decimal
    day_resets_at: datetime
    month_resets_at: datetime
    blocked_reason: str | None


class DaySpend(Spend):
    date: date


class ModelSpend(Spend):
    model: str
    operation: str
    priced: bool  # false when the model isn't on the price list (its calls add $0)


class StageSpend(Spend):
    source: str
    stage: str | None


class JobSpend(Spend):
    job_id: uuid.UUID
    ticker: str
    company: str
    status: str
    created_at: datetime


class CostSummary(BaseModel):
    budget: BudgetOut
    pricing_source: str
    pricing_checked: date
    all_time: Spend
    window_days: int
    window: Spend
    per_job_average: Decimal | None  # list price per completed research job
    days: list[DaySpend]
    models: list[ModelSpend]
    stages: list[StageSpend]
    jobs: list[JobSpend]
    unpriced_calls: int
    estimated_calls: int
    first_call_at: datetime | None
