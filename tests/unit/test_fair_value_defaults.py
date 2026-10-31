"""Default fair-value inputs from filings (ADR 0012): every number traceable to a reported line."""
from datetime import date
from decimal import Decimal

import pytest

from backend.analysis.metrics import FinancialPeriod
from backend.valuation.assumptions import GROWTH_CAP, LONG_RUN_GROWTH, default_inputs
from backend.valuation.fair_value import ValuationSkipped
from backend.valuation.market import RiskFreeRate

B = Decimal("1e9")
RF = RiskFreeRate(rate=Decimal("0.0450"), as_of=date(2026, 10, 30), source="test")


def year(fy, revenue, ocf, capex, sbc=None, op_income=None):
    return FinancialPeriod(
        fiscal_year=fy, revenue=revenue * B, operating_cash_flow=ocf * B, capital_expenditure=capex * B,
        share_based_compensation=sbc * B if sbc is not None else None,
        operating_income=(op_income if op_income is not None else revenue // 4) * B,
        income_tax_expense=2 * B, pretax_income=10 * B, interest_expense=Decimal("0"),
    )


def test_base_cash_flow_is_the_average_margin_on_the_latest_revenue():
    # A fast grower: FCF margins 10%, 20%, 30% on revenue 100 → 200 → 400.
    periods = [year(2022, 100, 12, 2), year(2023, 200, 45, 5), year(2024, 400, 125, 5)]

    inputs, _ = default_inputs(periods, shares=Decimal("1e9"), sic="3711", risk_free=RF)

    assert [h["fcf_margin"] for h in inputs.history] == [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
    assert inputs.base_fcf == Decimal("0.2") * 400 * B  # not the $ average (≈ $56.7B)
    assert "average free-cash-flow margin 20.0%" in inputs.sources["base_fcf"]


def test_stock_compensation_is_a_cost_and_its_absence_is_noted():
    inputs, notes = default_inputs([year(2023, 100, 30, 5), year(2024, 100, 30, 5, sbc=4)],
                                   shares=Decimal("1e9"), sic=None, risk_free=RF)

    assert [h["fcf"] for h in inputs.history] == [25 * B, 21 * B]
    assert any("FY2023: stock-based compensation not reported" in n for n in notes)


def test_growth_comes_from_the_revenue_record_capped_and_floored():
    fast, notes = default_inputs([year(2022, 100, 20, 5), year(2024, 400, 80, 5)], shares=B, sic=None, risk_free=RF)
    shrinking, _ = default_inputs([year(2022, 100, 20, 5), year(2024, 81, 20, 5)], shares=B, sic=None, risk_free=RF)

    assert fast.initial_growth == GROWTH_CAP and any("rarely lasts" in n for n in notes)
    assert shrinking.initial_growth == 0 and "floored at 0%" in shrinking.sources["initial_growth"]
    assert fast.stable_growth == LONG_RUN_GROWTH


def test_earnings_power_uses_the_average_operating_margin_and_drops_out_on_losses():
    profitable, _ = default_inputs([year(2023, 100, 20, 5, op_income=10), year(2024, 200, 40, 5, op_income=60)],
                                   shares=B, sic=None, risk_free=RF)
    losing, _ = default_inputs([year(2024, 100, 20, 5, op_income=-5)], shares=B, sic=None, risk_free=RF)

    assert profitable.normalised_operating_income == Decimal("0.2") * 200 * B  # margins 10% and 30%
    assert losing.normalised_operating_income is None


@pytest.mark.parametrize("kwargs, reason", [
    ({"shares": None}, "diluted share count"),
    ({"risk_free": None}, "risk-free rate"),
])
def test_missing_essentials_skip_with_a_reason(kwargs, reason):
    args = {"shares": B, "sic": None, "risk_free": RF, **kwargs}
    with pytest.raises(ValuationSkipped, match=reason):
        default_inputs([year(2024, 100, 20, 5)], **args)
