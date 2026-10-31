"""API shapes for the fair-value valuation (ADR 0012). Money and rates are Decimal; the client only formats them."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AssumptionOut(BaseModel):
    key: str
    label: str
    value: Decimal
    unit: str  # ratio, years, USD, shares, number
    source: str
    editable: bool


class FcfYear(BaseModel):
    fiscal_year: int
    operating_cash_flow: Decimal
    after_tax_interest: Decimal
    capital_expenditure: Decimal
    share_based_compensation: Decimal
    fcf: Decimal


class ProjectionRow(BaseModel):
    year: int
    fiscal_year: int
    growth: Decimal
    fcf: Decimal
    discount_factor: Decimal
    present_value: Decimal


class DcfOut(BaseModel):
    projection: list[ProjectionRow]
    terminal_value: Decimal
    terminal_present_value: Decimal
    terminal_share: Decimal
    present_value_of_fcf: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    value_per_share: Decimal


class EpvOut(BaseModel):
    normalised_after_tax_operating_income: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    value_per_share: Decimal


class CostOfCapitalOut(BaseModel):
    levered_beta: Decimal
    cost_of_equity: Decimal
    pre_tax_cost_of_debt: Decimal
    after_tax_cost_of_debt: Decimal
    cost_of_capital: Decimal


class SensitivityOut(BaseModel):
    cost_of_capital_deltas: list[Decimal]
    growth_deltas: list[Decimal]
    value_per_share: list[list[Decimal | None]]


class MarketPriceOut(BaseModel):
    price: Decimal
    as_of: datetime | None
    source: str  # "Cboe delayed quote ..." or "entered by you"


class PriceCheckOut(BaseModel):
    """A share price set against the fair-value range. Decision support, not a recommendation."""

    price: Decimal
    fair_value: Decimal
    range_low: Decimal
    range_high: Decimal
    gap: Decimal  # fair value / price - 1: positive means the estimate is above the price
    position: str  # below_range | within_range | above_range
    implied_growth: Decimal | None  # growth at which the cash-flow DCF equals the price
    explanation: str


class ValuationOut(BaseModel):
    job_id: uuid.UUID
    status: str  # valued or skipped
    skip_reason: str | None = None
    method: str
    calculation_version: str
    industry: str | None = None
    base_year: int | None = None
    fair_value: Decimal | None = None
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    methods_used: list[str] = []
    assumptions: list[AssumptionOut] = []
    cost_of_capital: CostOfCapitalOut | None = None
    fcf_history: list[FcfYear] = []
    dcf: DcfOut | None = None
    epv: EpvOut | None = None
    sensitivity: SensitivityOut | None = None
    warnings: list[str] = []
    what_if: bool = False
    overridden: list[str] = []
    market_price: MarketPriceOut | None = None
    price_check: PriceCheckOut | None = None
    created_at: datetime


class WhatIfRequest(BaseModel):
    """Assumptions a reader may change. Everything else (filings, Rf, betas) stays as stored, so results reproduce."""

    initial_growth: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("0.40"))
    high_growth_years: int | None = Field(default=None, ge=1, le=10)
    fade_years: int | None = Field(default=None, ge=0, le=10)
    stable_growth: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("0.05"))
    equity_risk_premium: Decimal | None = Field(default=None, ge=Decimal("0.02"), le=Decimal("0.10"))
    debt_to_capital: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("0.80"))
    market_price: Decimal | None = Field(
        default=None, gt=Decimal("0"), le=Decimal("1000000"),
        description="A share price to compare with, instead of the delayed quote.",
    )
