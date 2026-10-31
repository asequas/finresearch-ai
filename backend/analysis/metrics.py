"""Deterministic financial metrics (ADR 0005). Pure functions over Decimal inputs.

Every result carries its formula and the named inputs it used, so the UI can
show "how was this calculated" and the verifier can check numbers in claims.
Metrics whose inputs are missing or meaningless (zero/negative denominators)
are skipped with a reason, never guessed.
"""
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

CALCULATION_VERSION = "1.0"
_PRECISION = Decimal("1e-10")


@dataclass(frozen=True)
class FinancialPeriod:
    fiscal_year: int
    revenue: Decimal | None = None
    cost_of_revenue: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_income: Decimal | None = None
    net_income: Decimal | None = None
    operating_cash_flow: Decimal | None = None
    capital_expenditure: Decimal | None = None
    research_and_development: Decimal | None = None
    interest_expense: Decimal | None = None
    cash: Decimal | None = None
    current_assets: Decimal | None = None
    current_liabilities: Decimal | None = None
    total_assets: Decimal | None = None
    total_liabilities: Decimal | None = None
    stockholders_equity: Decimal | None = None
    debt: Decimal | None = None
    eps: Decimal | None = None
    # DCF inputs (ADR 0010); not used by the ratio metrics.
    depreciation_amortization: Decimal | None = None
    income_tax_expense: Decimal | None = None
    pretax_income: Decimal | None = None
    short_term_investments: Decimal | None = None
    lease_liabilities: Decimal | None = None
    minority_interest: Decimal | None = None

    @property
    def period(self) -> str:
        return f"FY{self.fiscal_year}"


@dataclass(frozen=True)
class MetricResult:
    key: str
    label: str
    period: str
    fiscal_year: int | None
    value: Decimal
    unit: str  # "ratio" | "USD" | "times" | "USD/share"
    formula: str
    inputs: dict = field(default_factory=dict)
    calculation_version: str = CALCULATION_VERSION


@dataclass(frozen=True)
class SkippedMetric:
    key: str
    period: str
    reason: str


@dataclass
class MetricsReport:
    results: list[MetricResult] = field(default_factory=list)
    skipped: list[SkippedMetric] = field(default_factory=list)

    def get(self, key: str, period: str) -> MetricResult | None:
        return next((r for r in self.results if r.key == key and r.period == period), None)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_PRECISION, rounding=ROUND_HALF_EVEN)


def _input(name: str, value: Decimal, period: str) -> dict:
    return {"name": name, "value": str(value), "period": period}


def _gross_profit(p: FinancialPeriod) -> tuple[Decimal | None, str]:
    if p.gross_profit is not None:
        return p.gross_profit, "gross_profit"
    if p.revenue is not None and p.cost_of_revenue is not None:
        return p.revenue - p.cost_of_revenue, "revenue - cost_of_revenue"
    return None, "gross_profit"


def _free_cash_flow(p: FinancialPeriod) -> Decimal | None:
    if p.operating_cash_flow is None or p.capital_expenditure is None:
        return None
    # SEC reports capex as a positive outflow (PaymentsToAcquirePropertyPlantAndEquipment).
    return p.operating_cash_flow - abs(p.capital_expenditure)


# ---- single-period ratios ---------------------------------------------------

@dataclass(frozen=True)
class _Ratio:
    key: str
    label: str
    numerator: str
    denominator: str
    unit: str = "ratio"
    require_positive_denominator: bool = True


_RATIOS = (
    _Ratio("operating_margin", "Operating margin", "operating_income", "revenue"),
    _Ratio("net_margin", "Net margin", "net_income", "revenue"),
    _Ratio("rd_intensity", "R&D as % of revenue", "research_and_development", "revenue"),
    _Ratio("current_ratio", "Current ratio", "current_assets", "current_liabilities", unit="times"),
    _Ratio("debt_to_equity", "Debt to equity", "debt", "stockholders_equity", unit="times"),
    _Ratio("interest_coverage", "Interest coverage", "operating_income", "interest_expense", unit="times"),
    _Ratio("liabilities_to_assets", "Liabilities to assets", "total_liabilities", "total_assets"),
)


def _ratio(spec: _Ratio, p: FinancialPeriod, out: MetricsReport) -> None:
    numerator = getattr(p, spec.numerator)
    denominator = getattr(p, spec.denominator)
    if numerator is None or denominator is None:
        missing = spec.numerator if numerator is None else spec.denominator
        out.skipped.append(SkippedMetric(spec.key, p.period, f"{missing} not reported"))
        return
    if denominator == 0 or (spec.require_positive_denominator and denominator < 0):
        out.skipped.append(SkippedMetric(spec.key, p.period, f"{spec.denominator} is not positive"))
        return
    out.results.append(
        MetricResult(
            key=spec.key,
            label=spec.label,
            period=p.period,
            fiscal_year=p.fiscal_year,
            value=_q(numerator / denominator),
            unit=spec.unit,
            formula=f"{spec.numerator} / {spec.denominator}",
            inputs={
                spec.numerator: _input(spec.numerator, numerator, p.period),
                spec.denominator: _input(spec.denominator, denominator, p.period),
            },
        )
    )


def _period_metrics(p: FinancialPeriod, out: MetricsReport) -> None:
    for spec in _RATIOS:
        _ratio(spec, p, out)

    gross_profit, gross_source = _gross_profit(p)
    if gross_profit is not None and p.revenue and p.revenue > 0:
        inputs = {"revenue": _input("revenue", p.revenue, p.period)}
        if gross_source == "gross_profit":
            inputs["gross_profit"] = _input("gross_profit", gross_profit, p.period)
        else:
            inputs["cost_of_revenue"] = _input("cost_of_revenue", p.cost_of_revenue, p.period)
        out.results.append(
            MetricResult(
                "gross_margin", "Gross margin", p.period, p.fiscal_year,
                _q(gross_profit / p.revenue), "ratio", f"({gross_source}) / revenue", inputs,
            )
        )
    else:
        out.skipped.append(SkippedMetric("gross_margin", p.period, "gross profit or revenue not reported"))

    fcf = _free_cash_flow(p)
    if fcf is None:
        out.skipped.append(SkippedMetric("free_cash_flow", p.period, "operating cash flow or capex not reported"))
        return
    fcf_inputs = {
        "operating_cash_flow": _input("operating_cash_flow", p.operating_cash_flow, p.period),
        "capital_expenditure": _input("capital_expenditure", abs(p.capital_expenditure), p.period),
    }
    out.results.append(
        MetricResult(
            "free_cash_flow", "Free cash flow", p.period, p.fiscal_year, _q(fcf), "USD",
            "operating_cash_flow - capital_expenditure", fcf_inputs,
        )
    )
    if p.revenue and p.revenue > 0:
        out.results.append(
            MetricResult(
                "fcf_margin", "Free cash flow margin", p.period, p.fiscal_year, _q(fcf / p.revenue), "ratio",
                "(operating_cash_flow - capital_expenditure) / revenue",
                {**fcf_inputs, "revenue": _input("revenue", p.revenue, p.period)},
            )
        )
    if p.net_income and p.net_income > 0:
        out.results.append(
            MetricResult(
                "fcf_conversion", "FCF conversion (FCF / net income)", p.period, p.fiscal_year,
                _q(fcf / p.net_income), "times",
                "(operating_cash_flow - capital_expenditure) / net_income",
                {**fcf_inputs, "net_income": _input("net_income", p.net_income, p.period)},
            )
        )

    if p.debt is not None and p.cash is not None:
        out.results.append(
            MetricResult(
                "net_debt", "Net debt (negative = net cash)", p.period, p.fiscal_year, _q(p.debt - p.cash), "USD",
                "debt - cash",
                {"debt": _input("debt", p.debt, p.period), "cash": _input("cash", p.cash, p.period)},
            )
        )


# ---- multi-period metrics ----------------------------------------------------

_GROWTH_FIELDS = (
    ("revenue_growth", "Revenue growth (YoY)", "revenue"),
    ("operating_income_growth", "Operating income growth (YoY)", "operating_income"),
    ("net_income_growth", "Net income growth (YoY)", "net_income"),
    ("eps_growth", "Diluted EPS growth (YoY)", "eps"),
)


def _growth(previous: FinancialPeriod, current: FinancialPeriod, out: MetricsReport) -> None:
    for key, label, name in _GROWTH_FIELDS:
        before, after = getattr(previous, name), getattr(current, name)
        if before is None or after is None:
            out.skipped.append(SkippedMetric(key, current.period, f"{name} missing for one of the years"))
            continue
        if before <= 0:
            out.skipped.append(SkippedMetric(key, current.period, f"prior-year {name} is not positive"))
            continue
        out.results.append(
            MetricResult(
                key, label, current.period, current.fiscal_year, _q((after - before) / before), "ratio",
                f"({name}[{current.period}] - {name}[{previous.period}]) / {name}[{previous.period}]",
                {
                    f"{name}_current": _input(name, after, current.period),
                    f"{name}_prior": _input(name, before, previous.period),
                },
            )
        )

    equity_now, equity_before = current.stockholders_equity, previous.stockholders_equity
    if current.net_income is not None and equity_now is not None and equity_before is not None:
        average_equity = (equity_now + equity_before) / 2
        if average_equity > 0:
            out.results.append(
                MetricResult(
                    "return_on_equity", "Return on average equity", current.period, current.fiscal_year,
                    _q(current.net_income / average_equity), "ratio",
                    f"net_income[{current.period}] / average(stockholders_equity[{previous.period}], "
                    f"stockholders_equity[{current.period}])",
                    {
                        "net_income": _input("net_income", current.net_income, current.period),
                        "equity_current": _input("stockholders_equity", equity_now, current.period),
                        "equity_prior": _input("stockholders_equity", equity_before, previous.period),
                    },
                )
            )
        else:
            out.skipped.append(SkippedMetric("return_on_equity", current.period, "average equity is not positive"))


def _cagr(first: FinancialPeriod, last: FinancialPeriod, out: MetricsReport) -> None:
    years = last.fiscal_year - first.fiscal_year
    period = f"{first.period}-{last.period}"
    if years < 2 or not first.revenue or not last.revenue or first.revenue <= 0 or last.revenue <= 0:
        out.skipped.append(SkippedMetric("revenue_cagr", period, "needs positive revenue at least two years apart"))
        return
    with localcontext() as context:
        context.prec = 34
        growth = (last.revenue / first.revenue) ** (Decimal(1) / Decimal(years)) - 1
    out.results.append(
        MetricResult(
            "revenue_cagr", f"Revenue CAGR ({years} years)", period, last.fiscal_year, _q(growth), "ratio",
            f"(revenue[{last.period}] / revenue[{first.period}]) ^ (1 / {years}) - 1",
            {
                "revenue_end": _input("revenue", last.revenue, last.period),
                "revenue_start": _input("revenue", first.revenue, first.period),
            },
        )
    )


def compute_metrics(periods: Sequence[FinancialPeriod]) -> MetricsReport:
    """Compute every metric for annual periods (any order; duplicates rejected)."""
    ordered = sorted(periods, key=lambda p: p.fiscal_year)
    years = [p.fiscal_year for p in ordered]
    if len(set(years)) != len(years):
        raise ValueError(f"duplicate fiscal years: {years}")

    out = MetricsReport()
    for period in ordered:
        _period_metrics(period, out)
    for previous, current in zip(ordered, ordered[1:]):
        if current.fiscal_year - previous.fiscal_year == 1:
            _growth(previous, current, out)
    if len(ordered) >= 3:
        _cagr(ordered[0], ordered[-1], out)
    return out


MetricFormatter = Callable[[Decimal], str]


def format_metric(value: Decimal, unit: str) -> str:
    """Human formatting used in prompts and the verifier's number matching."""
    if unit == "ratio":
        return f"{(value * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_EVEN)}%"
    if unit == "times":
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)}x"
    if unit == "USD":
        return format_usd(value)
    if unit == "USD/share":
        return f"${value.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN):,}"
    return str(value)


def describe_metric(key: str, value: Decimal, unit: str) -> str:
    """Reader-facing value: negative net debt is net cash, said in words rather than a minus sign."""
    if key == "net_debt" and value < 0:
        return f"net cash of {format_usd(-value)}"
    return format_metric(value, unit)


def format_usd(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    for threshold, suffix in ((Decimal("1e12"), "T"), (Decimal("1e9"), "B"), (Decimal("1e6"), "M")):
        if magnitude >= threshold:
            scaled = (magnitude / threshold).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            return f"{sign}${scaled}{suffix}"
    return f"{sign}${magnitude.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN):,}"
