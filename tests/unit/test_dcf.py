"""The DCF engine (ADR 0010), checked against Damodaran's own worked example first."""
from dataclasses import replace
from decimal import Decimal

import pytest

from backend.analysis.metrics import FinancialPeriod
from backend.valuation.dcf import (
    DcfInputs,
    InvalidAssumptions,
    ValuationSkipped,
    apply_overrides,
    capital_cost,
    fundamentals,
    value_firm,
)

D = Decimal

# Damodaran on Valuation, ch. 2, Illustrations 2.1-2.7: 3M in September 2008 ($ millions).
THREE_M = DcfInputs(
    base_year=2007, base_ebit=D("3586"), effective_tax_rate=D("0"), marginal_tax_rate=D("0"),  # after-tax EBIT given
    high_growth=D("0.075"), high_growth_years=5, transition_years=0, return_on_capital=D("0.25"),  # → 30% reinvestment
    stable_growth=D("0.03"), risk_free_rate=D("0.0372"), equity_risk_premium=D("0.04"), unlevered_beta=D("1.36"),
    debt_to_capital=D("0.085"), default_spread=D("0.0075"),
    cost_of_capital_override=D("0.0863"), stable_cost_of_capital_override=D("0.0676"),  # stable ROC = 6.76% → 44.4%
    cash=D("2475"), non_operating_assets=D("778"), debt=D("5297"), options_value=D("1216"), shares=D("699"),
)


def close(value: str, expected: str, tolerance: str = "0.002") -> bool:
    return abs(D(value) - D(expected)) / D(expected) <= D(tolerance)


def test_reproduces_damodarans_3m_valuation():
    result = value_firm(THREE_M)

    # The chapter rounds every intermediate year to $1M, so compare within 0.1%.
    fcff = [r["fcff"] for r in result["projection"]]
    assert all(close(ours, book, "0.001") for ours, book in zip(fcff, ["2698", "2900", "3118", "3352", "3603"]))
    assert close(result["derived"]["stable_reinvestment_rate"], "0.444")
    assert close(result["terminal"]["fcff"], "2947")
    assert close(result["terminal"]["value"], "78464")
    assert close(result["bridge"]["operating_value"], "64036")
    assert close(result["bridge"]["equity_value"], "60776")
    assert close(result["bridge"]["value_per_share"], "86.95")


def test_same_inputs_same_value():
    assert value_firm(THREE_M) == value_firm(DcfInputs.from_json(THREE_M.to_json()))


def test_cost_of_capital_from_its_parts():
    # Unlevered 0.9 at 20% debt: D/E 0.25, β_L = 0.9 × (1 + 0.75 × 0.25) = 1.06875.
    cost = capital_cost(risk_free=D("0.04"), erp=D("0.05"), unlevered_beta=D("0.9"), debt_to_capital=D("0.2"),
                        default_spread=D("0.01"), marginal_tax=D("0.25"))
    assert cost.levered_beta == D("1.06875")
    assert cost.cost_of_equity == D("0.0934375")  # 4% + 1.06875 × 5%
    assert cost.after_tax_cost_of_debt == D("0.0375")  # (4% + 1%) × 0.75
    assert cost.cost_of_capital == D("0.0822500")  # 0.8 × 9.34375% + 0.2 × 3.75%


def test_transition_fades_growth_tax_and_cost_of_capital_to_stable():
    inputs = replace(THREE_M, transition_years=5, effective_tax_rate=D("0.15"), marginal_tax_rate=D("0.25"))
    rows = value_firm(inputs, with_sensitivity=False)["projection"]

    assert [D(r["growth"]) for r in rows[4:]] == [D("0.075"), D("0.066"), D("0.057"), D("0.048"), D("0.039"), D("0.03")]
    assert D(rows[4]["tax_rate"]) == D("0.15") and D(rows[9]["tax_rate"]) == D("0.25")
    assert D(rows[9]["cost_of_capital"]) == D("0.0676")


def test_model_constraints_are_enforced():
    with pytest.raises(InvalidAssumptions, match="can't exceed the risk-free rate"):
        value_firm(replace(THREE_M, stable_growth=D("0.05")))
    with pytest.raises(InvalidAssumptions, match="below the stable cost of capital"):
        value_firm(replace(THREE_M, stable_growth=D("0.035"), stable_cost_of_capital_override=D("0.03")))
    with pytest.raises(ValuationSkipped, match="Operating income"):
        value_firm(replace(THREE_M, base_ebit=D("-10")))


def test_sensitivity_grid_brackets_the_base_case():
    result = value_firm(THREE_M)
    grid = result["sensitivity"]
    base_col = grid["stable_growths"].index("0.03")
    middle = grid["value_per_share"][2][base_col]

    assert middle == result["bridge"]["value_per_share"]
    assert "0.04" not in grid["stable_growths"]  # above the 3.72% risk-free rate
    column = [D(row[base_col]) for row in grid["value_per_share"]]
    assert column == sorted(column, reverse=True)  # higher cost of capital, lower value


def test_what_if_overrides_are_recorded_and_change_value():
    lower = apply_overrides(THREE_M, {"high_growth": D("0.03"), "stable_growth": None})

    assert lower.sources["high_growth"] == "what-if (user override)" and "stable_growth" not in lower.sources
    assert D(value_firm(lower)["bridge"]["value_per_share"]) < D("86.95")


def _period(year, **values):
    return FinancialPeriod(fiscal_year=year, **{k: D(str(v)) for k, v in values.items()})


def test_fundamental_growth_is_reinvestment_times_return_on_capital():
    periods = [
        _period(2022, operating_income=90, current_assets=300, cash=100, current_liabilities=150, stockholders_equity=500, debt=100),
        _period(2023, operating_income=100, capital_expenditure=60, depreciation_amortization=30, current_assets=320,
                cash=100, current_liabilities=150, stockholders_equity=520, debt=100, income_tax_expense=20, pretax_income=100),
    ]
    result = fundamentals(periods, marginal_tax=D("0.25"))

    # after-tax EBIT 80 (20% effective); reinvestment = (60-30) + (70-50) = 50 → 62.5%; ROC = 80 / (500+100-100) = 16%.
    assert result.reinvestment_rate == D("0.625")
    assert result.return_on_capital == D("0.16")
    assert result.growth == D("0.1") and result.method == "reinvestment rate × return on capital"


def test_fundamental_growth_falls_back_to_revenue_when_the_firm_shrinks_capital():
    periods = [
        _period(2021, revenue=100, operating_income=10, stockholders_equity=50),
        _period(2022, revenue=110, operating_income=11, capital_expenditure=1, depreciation_amortization=5, stockholders_equity=50),
        _period(2023, revenue=121, operating_income=12, capital_expenditure=1, depreciation_amortization=5, stockholders_equity=50),
    ]
    result = fundamentals(periods, marginal_tax=D("0.25"))

    assert result.method == "revenue CAGR (fallback)"
    assert abs(result.growth - D("0.10")) < D("0.0001")
