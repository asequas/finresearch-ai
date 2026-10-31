"""Default assumptions that depend on a company's competitive advantage and R&D (ADR 0011)."""
from datetime import date
from decimal import Decimal as D

from backend.analysis.metrics import FinancialPeriod
from backend.valuation.assumptions import default_inputs
from backend.valuation.market import RiskFreeRate

RF = RiskFreeRate(D("0.045"), date(2026, 10, 30), "test")


def periods(operating_income: str, equity: str, rd: str | None = None) -> list[FinancialPeriod]:
    def p(year, scale):
        return FinancialPeriod(
            fiscal_year=year, revenue=D("1000") * scale, operating_income=D(operating_income) * scale,
            stockholders_equity=D(equity), capital_expenditure=D("60") * scale, depreciation_amortization=D("30") * scale,
            current_assets=D("300"), current_liabilities=D("200"), cash=D("50"), income_tax_expense=D("20") * scale,
            pretax_income=D("100") * scale, research_and_development=D(rd) * scale if rd else None,
        )
    return [p(2022, D("0.9")), p(2023, D("0.95")), p(2024, D("1"))]


def test_a_wide_advantage_gets_ten_years_and_a_fading_excess_return():
    inputs, _ = default_inputs(periods("300", "400"), shares=D("100"), sic="7372", risk_free=RF)

    assert inputs.high_growth_years == 10
    assert inputs.stable_return_on_capital is not None and inputs.stable_return_on_capital <= D("0.25")


def test_an_ordinary_business_keeps_the_default_phases():
    inputs, _ = default_inputs(periods("60", "2000"), shares=D("100"), sic="5331", risk_free=RF)

    assert inputs.high_growth_years == 5


def test_material_rd_is_capitalised_with_the_industry_life():
    with_rd, _ = default_inputs(periods("300", "400", rd="150"), shares=D("100"), sic="7372", risk_free=RF)
    without, _ = default_inputs(periods("300", "400"), shares=D("100"), sic="7372", risk_free=RF)

    assert "3-year capitalisation" in with_rd.sources["base_ebit"]  # software: 3-year life
    assert with_rd.base_ebit > without.base_ebit  # growing R&D: spend exceeds amortisation
