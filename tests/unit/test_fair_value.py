"""Fair-value engine (ADR 0012): every number below is worked by hand."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from backend.valuation.fair_value import (
    FairValueInputs,
    InvalidAssumptions,
    ValuationSkipped,
    apply_overrides,
    capital_cost,
    implied_growth,
    value,
)

BASE = FairValueInputs(
    base_year=2024, base_fcf=D("100"), initial_growth=D("0.10"), high_growth_years=2, fade_years=0,
    stable_growth=D("0.02"), normalised_operating_income=D("200"), tax_rate=D("0.25"), risk_free_rate=D("0.04"),
    equity_risk_premium=D("0.05"), unlevered_beta=D("1"), debt_to_capital=D("0"), default_spread=D("0.01"),
    marginal_tax_rate=D("0.25"), cash=D("50"), non_operating_assets=D("0"), debt=D("30"), minority_interest=D("0"),
    shares=D("10"), cost_of_capital_override=D("0.10"),
)


def test_cash_flow_dcf_by_hand():
    dcf = value(BASE)["dcf"]
    # FCF 110 and 121, each worth 100 today at 10%; terminal 121 × 1.02 / 8% = 1,542.75, worth 1,275 today.
    assert [p["fcf"] for p in dcf["projection"]] == ["110.00", "121.00"]
    assert [p["present_value"] for p in dcf["projection"]] == ["100.00", "100.00"]
    assert dcf["terminal_value"] == "1542.75" and dcf["terminal_present_value"] == "1275.00"
    assert dcf["enterprise_value"] == "1475.00" and dcf["equity_value"] == "1495.00"  # + cash 50 − debt 30
    assert dcf["value_per_share"] == "149.50"


def test_earnings_power_value_by_hand():
    epv = value(BASE)["epv"]
    # 200 × (1 − 25%) = 150 a year with no growth, worth 1,500 at 10%; + 50 − 30 = 1,520 → 152.00 a share.
    assert (epv["normalised_after_tax_operating_income"], epv["enterprise_value"], epv["value_per_share"]) == ("150.00", "1500.00", "152.00")


def test_fair_value_is_the_mean_and_the_range_spans_the_methods():
    result = value(BASE)
    assert (result["fair_value"], result["range_low"], result["range_high"]) == ("150.75", "149.50", "152.00")
    assert result["methods_used"] == ["dcf", "epv"]


def test_reverse_dcf_recovers_the_growth_behind_a_price():
    assert abs(implied_growth(BASE, D("149.50")) - D("0.10")) < D("0.0002")
    assert implied_growth(BASE, D("100000")) is None  # beyond any plausible growth


def test_a_method_that_does_not_apply_drops_out_and_says_so():
    no_fcf = value(replace(BASE, base_fcf=D("-20")))
    assert no_fcf["dcf"] is None and no_fcf["fair_value"] == "152.00" and no_fcf["methods_used"] == ["epv"]
    assert any("free cash flow isn't positive" in w for w in no_fcf["warnings"])
    with pytest.raises(ValuationSkipped):
        value(replace(BASE, base_fcf=None, normalised_operating_income=D("-5")))


def test_model_constraints():
    with pytest.raises(InvalidAssumptions, match="below the cost of capital"):
        value(replace(BASE, stable_growth=D("0.035"), risk_free_rate=D("0.05"), cost_of_capital_override=D("0.03")))
    with pytest.raises(InvalidAssumptions, match="risk-free rate"):
        value(replace(BASE, stable_growth=D("0.045")))


def test_cost_of_capital_from_its_parts():
    cost = capital_cost(risk_free=D("0.04"), erp=D("0.05"), unlevered_beta=D("0.9"), debt_to_capital=D("0.2"),
                        default_spread=D("0.01"), marginal_tax=D("0.25"))
    assert (cost.levered_beta, cost.cost_of_equity, cost.after_tax_cost_of_debt, cost.cost_of_capital) == (
        D("1.06875"), D("0.0934375"), D("0.0375"), D("0.0822500"))


def test_sensitivity_grid_and_reproducibility():
    result = value(BASE)
    assert result["sensitivity"]["value_per_share"][2][2] == "149.50"  # the base cell
    assert value(FairValueInputs.from_json(BASE.to_json())) == result


def test_what_if_overrides_are_recorded():
    lower = apply_overrides(BASE, {"initial_growth": D("0.02")})
    assert lower.sources["initial_growth"] == "what-if (user override)"
    assert D(value(lower)["dcf"]["value_per_share"]) < D("149.50")
