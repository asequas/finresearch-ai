"""API shapes for the DCF valuation (ADR 0010). Money and rates are Decimal; the client only formats them."""
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
    editable: bool  # can be changed in a what-if


class ProjectionRow(BaseModel):
    year: int
    fiscal_year: int
    growth: Decimal
    tax_rate: Decimal
    ebit: Decimal
    after_tax_ebit: Decimal
    reinvestment_rate: Decimal
    reinvestment: Decimal
    fcff: Decimal
    cost_of_capital: Decimal
    present_value: Decimal


class TerminalOut(BaseModel):
    after_tax_ebit: Decimal
    reinvestment_rate: Decimal
    fcff: Decimal
    value: Decimal
    present_value: Decimal
    share_of_operating_value: Decimal


class BridgeOut(BaseModel):
    present_value_of_fcff: Decimal
    present_value_of_terminal: Decimal
    operating_value: Decimal
    cash: Decimal
    non_operating_assets: Decimal
    debt: Decimal
    lease_liabilities: Decimal
    minority_interest: Decimal
    options_value: Decimal
    equity_value: Decimal
    shares: Decimal
    value_per_share: Decimal


class DerivedOut(BaseModel):
    levered_beta: Decimal
    cost_of_equity: Decimal
    pre_tax_cost_of_debt: Decimal
    after_tax_cost_of_debt: Decimal
    cost_of_capital: Decimal
    stable_cost_of_equity: Decimal
    stable_cost_of_capital: Decimal
    reinvestment_rate: Decimal
    stable_reinvestment_rate: Decimal
    stable_return_on_capital: Decimal


class SensitivityOut(BaseModel):
    cost_of_capital_deltas: list[Decimal]
    stable_growths: list[Decimal]
    value_per_share: list[list[Decimal | None]]


class ValuationOut(BaseModel):
    job_id: uuid.UUID
    status: str  # valued or skipped
    skip_reason: str | None = None
    method: str
    calculation_version: str
    industry: str | None = None
    base_year: int | None = None
    value_per_share: Decimal | None = None
    range_low: Decimal | None = None  # across ±0.5% cost of capital and ±0.5% stable growth
    range_high: Decimal | None = None
    equity_value: Decimal | None = None
    operating_value: Decimal | None = None
    assumptions: list[AssumptionOut] = []
    derived: DerivedOut | None = None
    projection: list[ProjectionRow] = []
    terminal: TerminalOut | None = None
    bridge: BridgeOut | None = None
    sensitivity: SensitivityOut | None = None
    warnings: list[str] = []
    what_if: bool = False
    overridden: list[str] = []
    created_at: datetime


class WhatIfRequest(BaseModel):
    """Assumptions a reader may change. Everything else (Rf, betas, filings) stays as stored, so results reproduce."""

    high_growth: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("0.40"))
    high_growth_years: int | None = Field(default=None, ge=1, le=10)
    transition_years: int | None = Field(default=None, ge=0, le=10)
    return_on_capital: Decimal | None = Field(default=None, ge=Decimal("0.01"), le=Decimal("1"))
    stable_growth: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("0.06"))
    stable_return_on_capital: Decimal | None = Field(default=None, ge=Decimal("0.01"), le=Decimal("1"))
    equity_risk_premium: Decimal | None = Field(default=None, ge=Decimal("0.02"), le=Decimal("0.10"))
    debt_to_capital: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("0.80"))
