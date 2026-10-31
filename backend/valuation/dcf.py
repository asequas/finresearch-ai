"""Discounted cash flow valuation: free cash flow to the firm (ADR 0010).

Follows Damodaran, *Damodaran on Valuation* (2nd ed.), ch. 2 "Intrinsic Valuation":

    FCFF            = EBIT (1 - t) (1 - reinvestment rate)
    reinvestment    = growth / return on capital           (growth has to be paid for)
    cost of capital = E/V × (Rf + β_L × ERP) + D/V × (Rf + default spread)(1 - t_marginal)
    β_L             = β_unlevered × (1 + (1 - t_marginal) × D/E)
    terminal value  = FCFF_{n+1} / (cost of capital_stable - g_stable),  g_stable ≤ Rf
    equity          = operating value + cash + non-operating assets - debt - leases - minority interest - options

Three phases: high growth, a linear transition (growth, reinvestment, cost of capital and tax move to their stable
values) and stable growth. Pure functions over Decimal; nothing here does I/O or calls a model.
"""
from dataclasses import asdict, dataclass, field, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from backend.analysis.metrics import FinancialPeriod

CALCULATION_VERSION = "dcf-1.0"
GROWTH_CAP = Decimal("0.20")
RATE = Decimal("0.000001")
MONEY = Decimal("0.01")
SENSITIVITY_WACC_DELTAS = [Decimal(d) for d in ("-0.01", "-0.005", "0", "0.005", "0.01")]
SENSITIVITY_STABLE_GROWTHS = [Decimal(g) for g in ("0.02", "0.025", "0.03", "0.035", "0.04")]


class ValuationSkipped(Exception):
    """The inputs can't support a DCF (for example an operating loss). The message says why, for the reader."""


class InvalidAssumptions(ValueError):
    """An assumption breaks the model's constraints (stable growth above the risk-free rate, or ≥ cost of capital)."""


@dataclass(frozen=True)
class DcfInputs:
    """Everything a valuation depends on. Stored with the valuation, so it can be reproduced and what-if'd."""

    base_year: int
    base_ebit: Decimal  # pre-tax operating income in the base year
    effective_tax_rate: Decimal
    marginal_tax_rate: Decimal
    high_growth: Decimal
    high_growth_years: int
    transition_years: int
    return_on_capital: Decimal  # on new investment during high growth; reinvestment = growth / ROC
    stable_growth: Decimal
    risk_free_rate: Decimal
    equity_risk_premium: Decimal
    unlevered_beta: Decimal
    debt_to_capital: Decimal  # D / (D + E)
    default_spread: Decimal
    stable_beta: Decimal = Decimal("1.0")  # mature firms drift towards the market
    stable_return_on_capital: Decimal | None = None  # None: = stable cost of capital (no excess returns)
    cost_of_capital_override: Decimal | None = None  # use instead of the CAPM build-up (high growth)
    stable_cost_of_capital_override: Decimal | None = None
    reinvestment_rate_override: Decimal | None = None
    cash: Decimal = Decimal("0")
    non_operating_assets: Decimal = Decimal("0")  # short-term investments, cross holdings
    debt: Decimal = Decimal("0")
    lease_liabilities: Decimal = Decimal("0")
    minority_interest: Decimal = Decimal("0")
    options_value: Decimal = Decimal("0")
    shares: Decimal = Decimal("1")
    sources: dict = field(default_factory=dict)  # field name -> where the value came from

    def to_json(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    @classmethod
    def from_json(cls, data: dict) -> "DcfInputs":
        decimals = {f.name for f in fields(cls) if "Decimal" in str(f.type)}
        values = {k: (Decimal(v) if k in decimals and v is not None else v) for k, v in data.items() if k in {f.name for f in fields(cls)}}
        return cls(**values)


@dataclass(frozen=True)
class CapitalCost:
    levered_beta: Decimal
    cost_of_equity: Decimal
    pre_tax_cost_of_debt: Decimal
    after_tax_cost_of_debt: Decimal
    debt_to_capital: Decimal
    cost_of_capital: Decimal


def capital_cost(*, risk_free: Decimal, erp: Decimal, unlevered_beta: Decimal | None, levered_beta: Decimal | None = None,
                 debt_to_capital: Decimal, default_spread: Decimal, marginal_tax: Decimal) -> CapitalCost:
    """Cost of capital from its parts. Pass `levered_beta` to fix the equity beta (stable phase)."""
    if not Decimal("0") <= debt_to_capital < Decimal("1"):
        raise InvalidAssumptions("The debt ratio must be at least 0% and below 100%.")
    de = debt_to_capital / (1 - debt_to_capital)
    beta = levered_beta if levered_beta is not None else unlevered_beta * (1 + (1 - marginal_tax) * de)
    cost_of_equity = risk_free + beta * erp
    pre_tax_debt = risk_free + default_spread
    after_tax_debt = pre_tax_debt * (1 - marginal_tax)
    wacc = cost_of_equity * (1 - debt_to_capital) + after_tax_debt * debt_to_capital
    return CapitalCost(beta, cost_of_equity, pre_tax_debt, after_tax_debt, debt_to_capital, wacc)


def _fade(start: Decimal, end: Decimal, year: int, high_years: int, transition_years: int) -> Decimal:
    """High-growth value, then a straight line to the stable value across the transition."""
    if year <= high_years:
        return start
    step = year - high_years
    if transition_years == 0 or step >= transition_years:
        return end
    return start + (end - start) * Decimal(step) / Decimal(transition_years)


def _q(value: Decimal, unit: Decimal = RATE) -> Decimal:
    return value.quantize(unit, rounding=ROUND_HALF_EVEN)


def value_firm(inputs: DcfInputs, *, with_sensitivity: bool = True) -> dict:
    """Value the firm and its equity per share. Returns a JSON-ready dict (Decimals as strings)."""
    with localcontext() as context:
        context.prec = 34
        return _value(inputs, with_sensitivity)


def _value(i: DcfInputs, with_sensitivity: bool) -> dict:
    if i.base_ebit <= 0:
        raise ValuationSkipped("Operating income is zero or negative, so free cash flow to the firm can't be projected from it.")
    if i.shares <= 0:
        raise ValuationSkipped("No share count was reported, so value per share can't be computed.")
    if i.stable_growth > i.risk_free_rate:
        raise InvalidAssumptions(
            f"Stable growth ({i.stable_growth:.2%}) can't exceed the risk-free rate ({i.risk_free_rate:.2%}): "
            "no firm can outgrow the economy forever."
        )
    if i.high_growth_years < 1 or i.transition_years < 0 or i.high_growth_years + i.transition_years > 20:
        raise InvalidAssumptions("Use 1-10 high-growth years and 0-10 transition years.")

    high = capital_cost(risk_free=i.risk_free_rate, erp=i.equity_risk_premium, unlevered_beta=i.unlevered_beta,
                        debt_to_capital=i.debt_to_capital, default_spread=i.default_spread, marginal_tax=i.marginal_tax_rate)
    stable = capital_cost(risk_free=i.risk_free_rate, erp=i.equity_risk_premium, unlevered_beta=None,
                          levered_beta=i.stable_beta, debt_to_capital=i.debt_to_capital,
                          default_spread=i.default_spread, marginal_tax=i.marginal_tax_rate)
    wacc_high = i.cost_of_capital_override if i.cost_of_capital_override is not None else high.cost_of_capital
    wacc_stable = i.stable_cost_of_capital_override if i.stable_cost_of_capital_override is not None else stable.cost_of_capital
    if wacc_stable <= i.stable_growth:
        raise InvalidAssumptions(
            f"Stable growth ({i.stable_growth:.2%}) must be below the stable cost of capital ({wacc_stable:.2%})."
        )
    roc_stable = i.stable_return_on_capital if i.stable_return_on_capital is not None else wacc_stable
    if i.return_on_capital <= 0 or roc_stable <= 0:
        raise InvalidAssumptions("Return on capital must be positive.")
    rr_high = i.reinvestment_rate_override if i.reinvestment_rate_override is not None else i.high_growth / i.return_on_capital
    rr_stable = i.stable_growth / roc_stable

    warnings: list[str] = []
    rows = []
    ebit = i.base_ebit
    cumulative = Decimal("1")
    years = i.high_growth_years + i.transition_years
    for year in range(1, years + 1):
        growth = _fade(i.high_growth, i.stable_growth, year, i.high_growth_years, i.transition_years)
        tax = _fade(i.effective_tax_rate, i.marginal_tax_rate, year, i.high_growth_years, i.transition_years)
        rr = _fade(rr_high, rr_stable, year, i.high_growth_years, i.transition_years)
        wacc = _fade(wacc_high, wacc_stable, year, i.high_growth_years, i.transition_years)
        ebit = ebit * (1 + growth)
        after_tax = ebit * (1 - tax)
        reinvestment = after_tax * rr
        fcff = after_tax - reinvestment
        cumulative = cumulative * (1 + wacc)
        pv = fcff / cumulative
        rows.append({
            "year": year, "fiscal_year": i.base_year + year, "growth": growth, "tax_rate": tax, "ebit": ebit,
            "after_tax_ebit": after_tax, "reinvestment_rate": rr, "reinvestment": reinvestment, "fcff": fcff,
            "cost_of_capital": wacc, "cumulative_discount": cumulative, "present_value": pv,
        })
        if fcff < 0:
            warnings.append(f"Free cash flow is negative in {i.base_year + year}: reinvestment exceeds after-tax operating income.")

    terminal_after_tax = ebit * (1 + i.stable_growth) * (1 - i.marginal_tax_rate)
    terminal_fcff = terminal_after_tax * (1 - rr_stable)
    terminal_value = terminal_fcff / (wacc_stable - i.stable_growth)
    terminal_pv = terminal_value / cumulative
    explicit_pv = sum((r["present_value"] for r in rows), Decimal("0"))
    operating_value = explicit_pv + terminal_pv
    equity = (operating_value + i.cash + i.non_operating_assets - i.debt - i.lease_liabilities
              - i.minority_interest - i.options_value)
    per_share = equity / i.shares
    terminal_share = terminal_pv / operating_value if operating_value else Decimal("0")
    if terminal_share > Decimal("0.85"):
        warnings.append(f"The terminal value is {terminal_share:.0%} of operating value, so the stable-growth assumptions dominate.")
    if equity <= 0:
        warnings.append("Debt and other claims exceed the value of the operating assets: the equity has no intrinsic value here.")

    result = {
        "calculation_version": CALCULATION_VERSION,
        "inputs": i.to_json(),
        "derived": {
            "levered_beta": _q(high.levered_beta), "cost_of_equity": _q(high.cost_of_equity),
            "pre_tax_cost_of_debt": _q(high.pre_tax_cost_of_debt), "after_tax_cost_of_debt": _q(high.after_tax_cost_of_debt),
            "cost_of_capital": _q(wacc_high), "stable_cost_of_equity": _q(stable.cost_of_equity),
            "stable_cost_of_capital": _q(wacc_stable), "reinvestment_rate": _q(rr_high),
            "stable_reinvestment_rate": _q(rr_stable), "stable_return_on_capital": _q(roc_stable),
        },
        "projection": [
            {k: (_q(v, MONEY) if k in {"ebit", "after_tax_ebit", "reinvestment", "fcff", "present_value"}
                 else _q(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
            for row in rows
        ],
        "terminal": {
            "after_tax_ebit": _q(terminal_after_tax, MONEY), "reinvestment_rate": _q(rr_stable), "fcff": _q(terminal_fcff, MONEY),
            "value": _q(terminal_value, MONEY), "present_value": _q(terminal_pv, MONEY), "share_of_operating_value": _q(terminal_share),
        },
        "bridge": {
            "present_value_of_fcff": _q(explicit_pv, MONEY), "present_value_of_terminal": _q(terminal_pv, MONEY),
            "operating_value": _q(operating_value, MONEY), "cash": _q(i.cash, MONEY),
            "non_operating_assets": _q(i.non_operating_assets, MONEY), "debt": _q(i.debt, MONEY),
            "lease_liabilities": _q(i.lease_liabilities, MONEY), "minority_interest": _q(i.minority_interest, MONEY),
            "options_value": _q(i.options_value, MONEY), "equity_value": _q(equity, MONEY), "shares": i.shares,
            "value_per_share": _q(per_share, MONEY),
        },
        "warnings": warnings,
    }
    if with_sensitivity:
        result["sensitivity"] = sensitivity(i, wacc_high, wacc_stable)
    return _stringify(result)


def sensitivity(i: DcfInputs, wacc_high: Decimal, wacc_stable: Decimal) -> dict:
    """Value per share as the cost of capital (all phases) and stable growth move. None where the model breaks."""
    growths = sorted({g for g in SENSITIVITY_STABLE_GROWTHS if g <= i.risk_free_rate} | {i.stable_growth})
    grid = []
    for delta in SENSITIVITY_WACC_DELTAS:
        row = []
        for g in growths:
            trial = replace(i, stable_growth=g, cost_of_capital_override=wacc_high + delta,
                            stable_cost_of_capital_override=wacc_stable + delta)
            try:
                row.append(Decimal(value_firm(trial, with_sensitivity=False)["bridge"]["value_per_share"]))
            except (InvalidAssumptions, ValuationSkipped):
                row.append(None)
        grid.append(row)
    return {"cost_of_capital_deltas": SENSITIVITY_WACC_DELTAS, "stable_growths": growths, "value_per_share": grid}


def _stringify(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _stringify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify(v) for v in value]
    return value


# ---- Default assumptions from reported financials -------------------------------------------------------------

@dataclass(frozen=True)
class Fundamentals:
    """What the filings say about growth: how much of after-tax operating income is reinvested, and how well."""

    reinvestment_rate: Decimal | None
    return_on_capital: Decimal | None
    growth: Decimal
    method: str
    years: list[int]
    notes: list[str]


def _nwc(p: FinancialPeriod) -> Decimal | None:
    if p.current_assets is None or p.current_liabilities is None:
        return None
    return p.current_assets - (p.cash or 0) - (p.short_term_investments or 0) - p.current_liabilities


def _invested_capital(p: FinancialPeriod) -> Decimal | None:
    if p.stockholders_equity is None:
        return None
    return (p.stockholders_equity + (p.debt or 0) + (p.lease_liabilities or 0)
            - (p.cash or 0) - (p.short_term_investments or 0))


def effective_tax_rate(p: FinancialPeriod, marginal: Decimal) -> tuple[Decimal, str]:
    if p.income_tax_expense is not None and p.pretax_income and p.pretax_income > 0:
        rate = min(max(p.income_tax_expense / p.pretax_income, Decimal("0")), marginal)
        return rate, f"income tax ÷ pre-tax income, FY{p.fiscal_year} (capped at the marginal rate)"
    return marginal, "marginal rate (effective rate not reported)"


def fundamentals(periods: list[FinancialPeriod], marginal_tax: Decimal) -> Fundamentals:
    """Expected growth = reinvestment rate × return on capital, over up to the last 3 years (smooths lumpy capex)."""
    periods = sorted(periods, key=lambda p: p.fiscal_year)
    notes: list[str] = []
    window = [(prev, cur) for prev, cur in zip(periods, periods[1:]) if cur.operating_income is not None][-3:]
    reinvested = after_tax_total = Decimal("0")
    used_years = []
    for prev, cur in window:
        tax, _ = effective_tax_rate(cur, marginal_tax)
        after_tax = cur.operating_income * (1 - tax)
        if cur.capital_expenditure is None:
            continue
        net_capex = cur.capital_expenditure - (cur.depreciation_amortization or 0)
        if cur.depreciation_amortization is None:
            notes.append(f"FY{cur.fiscal_year}: depreciation not reported, so net capex = capex (conservative).")
        now, before = _nwc(cur), _nwc(prev)
        delta_wc = (now - before) if now is not None and before is not None else Decimal("0")
        reinvested += net_capex + delta_wc
        after_tax_total += after_tax
        used_years.append(cur.fiscal_year)

    rr = reinvested / after_tax_total if after_tax_total > 0 else None
    roc = None
    if len(periods) >= 2 and periods[-1].operating_income is not None:
        capital = _invested_capital(periods[-2])
        tax, _ = effective_tax_rate(periods[-1], marginal_tax)
        if capital and capital > 0:
            roc = periods[-1].operating_income * (1 - tax) / capital

    if rr is not None and roc is not None and rr > 0:
        growth = min(max(rr * roc, Decimal("0")), GROWTH_CAP)
        method = "reinvestment rate × return on capital"
        if rr * roc > GROWTH_CAP:
            notes.append(f"Fundamental growth of {rr * roc:.1%} capped at {GROWTH_CAP:.0%}.")
        return Fundamentals(rr, roc, growth, method, used_years, notes)

    # Fallback: the firm isn't reinvesting (or capital isn't meaningful); use recent revenue growth instead.
    revenues = [p for p in periods if p.revenue and p.revenue > 0]
    growth = Decimal("0")
    if len(revenues) >= 2:
        span = revenues[-1].fiscal_year - revenues[max(0, len(revenues) - 4)].fiscal_year
        first = revenues[max(0, len(revenues) - 4)].revenue
        if span > 0:
            growth = (revenues[-1].revenue / first) ** (Decimal(1) / Decimal(span)) - 1
    growth = min(max(growth, Decimal("0")), GROWTH_CAP)
    notes.append("Reinvestment is negative or capital isn't meaningful, so growth falls back to the recent revenue CAGR.")
    return Fundamentals(rr, roc, growth, "revenue CAGR (fallback)", used_years, notes)


def apply_overrides(inputs: DcfInputs, overrides: dict) -> DcfInputs:
    """A what-if: same stored inputs, some assumptions replaced. Sources say which ones the user changed."""
    clean = {k: v for k, v in overrides.items() if v is not None}
    sources = dict(inputs.sources)
    for key in clean:
        sources[key] = "what-if (user override)"
    return replace(inputs, **clean, sources=sources)
