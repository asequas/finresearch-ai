from decimal import Decimal as D

import pytest

from backend.analysis.metrics import FinancialPeriod, compute_metrics, describe_metric, format_metric, format_usd


def period(year, **values):
    return FinancialPeriod(fiscal_year=year, **{k: D(str(v)) for k, v in values.items()})


FY23 = period(
    2023, revenue=1000, gross_profit=600, operating_income=250, net_income=200, operating_cash_flow=300,
    capital_expenditure=80, research_and_development=150, interest_expense=10, cash=500, debt=400,
    current_assets=800, current_liabilities=400, total_assets=2000, total_liabilities=1200,
    stockholders_equity=800, eps=2,
)
FY24 = period(
    2024, revenue=1200, cost_of_revenue=420, operating_income=360, net_income=270, operating_cash_flow=390,
    capital_expenditure=-90, research_and_development=180, interest_expense=12, cash=650, debt=300,
    current_assets=900, current_liabilities=450, total_assets=2300, total_liabilities=1300,
    stockholders_equity=1000, eps=D("2.7"),
)


def value(report, key, period_label):
    result = report.get(key, period_label)
    assert result is not None, f"{key} {period_label} missing; skipped={report.skipped}"
    return result.value


def test_single_period_ratios():
    report = compute_metrics([FY23])

    assert value(report, "gross_margin", "FY2023") == D("0.6")
    assert value(report, "operating_margin", "FY2023") == D("0.25")
    assert value(report, "net_margin", "FY2023") == D("0.2")
    assert value(report, "rd_intensity", "FY2023") == D("0.15")
    assert value(report, "current_ratio", "FY2023") == D("2")
    assert value(report, "debt_to_equity", "FY2023") == D("0.5")
    assert value(report, "interest_coverage", "FY2023") == D("25")
    assert value(report, "liabilities_to_assets", "FY2023") == D("0.6")


def test_gross_margin_falls_back_to_revenue_minus_cost():
    result = compute_metrics([FY24]).get("gross_margin", "FY2024")

    assert result.value == D("0.65")
    assert result.formula == "(revenue - cost_of_revenue) / revenue"
    assert set(result.inputs) == {"revenue", "cost_of_revenue"}


def test_free_cash_flow_treats_capex_sign_consistently():
    report = compute_metrics([FY23, FY24])

    assert value(report, "free_cash_flow", "FY2023") == D("220")
    assert value(report, "free_cash_flow", "FY2024") == D("300")  # capex reported negative
    assert value(report, "fcf_margin", "FY2024") == D("0.25")
    assert value(report, "fcf_conversion", "FY2023") == D("1.1")


def test_net_debt_negative_means_net_cash():
    assert value(compute_metrics([FY24]), "net_debt", "FY2024") == D("-350")


def test_yoy_growth_and_return_on_equity():
    report = compute_metrics([FY24, FY23])  # order shouldn't matter

    assert value(report, "revenue_growth", "FY2024") == D("0.2")
    assert value(report, "operating_income_growth", "FY2024") == D("0.44")
    assert value(report, "net_income_growth", "FY2024") == D("0.35")
    assert value(report, "eps_growth", "FY2024") == D("0.35")
    assert value(report, "return_on_equity", "FY2024") == D("0.3")  # 270 / avg(800, 1000)


def test_growth_skipped_across_gap_years():
    report = compute_metrics([FY23, period(2025, revenue=1500)])

    assert report.get("revenue_growth", "FY2025") is None


def test_cagr_over_four_years():
    periods = [period(2020, revenue=100), period(2021, revenue=110), period(2022, revenue=120), period(2024, revenue=200)]

    cagr = value(compute_metrics(periods), "revenue_cagr", "FY2020-FY2024")

    assert abs(cagr - D("0.1892071150")) < D("1e-9")  # 2 ** (1/4) - 1


def test_missing_inputs_are_skipped_with_reason():
    report = compute_metrics([period(2024, revenue=100)])

    reasons = {(s.key, s.reason) for s in report.skipped}
    assert ("operating_margin", "operating_income not reported") in reasons
    assert report.get("operating_margin", "FY2024") is None


def test_non_positive_denominators_are_skipped():
    report = compute_metrics(
        [period(2023, net_income=-50, stockholders_equity=-10, debt=100), period(2024, net_income=10, revenue=0)]
    )

    assert report.get("debt_to_equity", "FY2023") is None
    assert report.get("net_income_growth", "FY2024") is None
    assert report.get("net_margin", "FY2024") is None


def test_duplicate_years_rejected():
    with pytest.raises(ValueError):
        compute_metrics([FY23, FY23])


def test_results_are_decimal_with_formula_and_inputs():
    for result in compute_metrics([FY23, FY24]).results:
        assert isinstance(result.value, D)
        assert result.formula
        assert result.inputs
        assert result.calculation_version == "1.0"


@pytest.mark.parametrize(
    "amount, expected",
    [(D("245122000000"), "$245.12B"), (D("-350000000"), "-$350.00M"), (D("3.2e12"), "$3.20T"), (D("950"), "$950")],
)
def test_format_usd(amount, expected):
    assert format_usd(amount) == expected


def test_format_metric_units():
    assert format_metric(D("0.4462"), "ratio") == "44.6%"
    assert format_metric(D("2.345"), "times") == "2.34x"


def test_negative_net_debt_is_described_as_net_cash():
    assert describe_metric("net_debt", D("-2140000000"), "USD") == "net cash of $2.14B"
    assert describe_metric("net_debt", D("350000000"), "USD") == "$350.00M"
    assert describe_metric("operating_margin", D("0.468"), "ratio") == "46.8%"
