"""Fair value as a blend of two simple, stable methods, plus the growth the price implies (ADR 0012).

1. Cash-flow DCF on *reported* free cash flow to the firm:
       FCFF = cash from operations + interest × (1 − t) − capital expenditure − stock-based compensation
   averaged over the last three years, grown at the company's own revenue growth record (held, then faded to a
   long-run rate), discounted at the cost of capital.
2. Earnings power value (Greenwald): what today's normalised after-tax operating profit is worth with no growth,
       EPV = average operating margin × latest revenue × (1 − t) / cost of capital.
3. Reverse DCF: the growth rate at which the cash-flow DCF equals a given share price.

Fair value = the mean of the methods that apply; the fair range spans them. Every input comes from the filings or
dated reference data. Pure functions over Decimal; no I/O, no model calls.
"""
from dataclasses import asdict, dataclass, field, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

CALCULATION_VERSION = "fv-2.0"
MONEY = Decimal("0.01")
RATE = Decimal("0.000001")
SENSITIVITY_WACC_DELTAS = [Decimal(d) for d in ("-0.01", "-0.005", "0", "0.005", "0.01")]
SENSITIVITY_GROWTH_DELTAS = [Decimal(d) for d in ("-0.04", "-0.02", "0", "0.02", "0.04")]


class InvalidAssumptions(ValueError):
    """An assumption breaks the model (long-run growth at or above the cost of capital, a negative period, ...)."""


class ValuationSkipped(Exception):
    """No method can value this company from its filings. The message says why, for the reader."""


@dataclass(frozen=True)
class CapitalCost:
    levered_beta: Decimal
    cost_of_equity: Decimal
    pre_tax_cost_of_debt: Decimal
    after_tax_cost_of_debt: Decimal
    debt_to_capital: Decimal
    cost_of_capital: Decimal


def capital_cost(*, risk_free: Decimal, erp: Decimal, unlevered_beta: Decimal, debt_to_capital: Decimal,
                 default_spread: Decimal, marginal_tax: Decimal) -> CapitalCost:
    """E/V × (Rf + β_L × ERP) + D/V × (Rf + spread)(1 − t), with β_L = β_u × (1 + (1 − t) × D/E)."""
    if not Decimal("0") <= debt_to_capital < Decimal("1"):
        raise InvalidAssumptions("The debt ratio must be at least 0% and below 100%.")
    de = debt_to_capital / (1 - debt_to_capital)
    beta = unlevered_beta * (1 + (1 - marginal_tax) * de)
    cost_of_equity = risk_free + beta * erp
    pre_tax_debt = risk_free + default_spread
    after_tax_debt = pre_tax_debt * (1 - marginal_tax)
    wacc = cost_of_equity * (1 - debt_to_capital) + after_tax_debt * debt_to_capital
    return CapitalCost(beta, cost_of_equity, pre_tax_debt, after_tax_debt, debt_to_capital, wacc)


@dataclass(frozen=True)
class FairValueInputs:
    """Everything a valuation depends on, stored with it so it reproduces and what-ifs start from the same data."""

    base_year: int
    base_fcf: Decimal | None  # average reported FCFF over the last 3 years; None when it can't be measured
    initial_growth: Decimal  # from the revenue record
    high_growth_years: int
    fade_years: int
    stable_growth: Decimal
    normalised_operating_income: Decimal | None  # average operating margin × latest revenue; None if negative
    tax_rate: Decimal
    risk_free_rate: Decimal
    equity_risk_premium: Decimal
    unlevered_beta: Decimal
    debt_to_capital: Decimal
    default_spread: Decimal
    marginal_tax_rate: Decimal
    cash: Decimal
    non_operating_assets: Decimal
    debt: Decimal
    minority_interest: Decimal
    shares: Decimal
    cost_of_capital_override: Decimal | None = None
    sources: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # per-year FCFF build-up, for display

    def to_json(self) -> dict:
        return _stringify(asdict(self))

    @classmethod
    def from_json(cls, data: dict) -> "FairValueInputs":
        decimals = {f.name for f in fields(cls) if "Decimal" in str(f.type)}
        known = {f.name for f in fields(cls)}
        return cls(**{k: (Decimal(v) if k in decimals and v is not None else v) for k, v in data.items() if k in known})


def _q(value: Decimal, unit: Decimal = RATE) -> Decimal:
    return value.quantize(unit, rounding=ROUND_HALF_EVEN)


def _stringify(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _stringify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stringify(v) for v in value]
    return value


def _growth(i: FairValueInputs, year: int) -> Decimal:
    if year <= i.high_growth_years:
        return i.initial_growth
    step = year - i.high_growth_years
    if i.fade_years == 0 or step >= i.fade_years:
        return i.stable_growth
    return i.initial_growth + (i.stable_growth - i.initial_growth) * Decimal(step) / Decimal(i.fade_years)


def _equity_per_share(i: FairValueInputs, enterprise_value: Decimal) -> tuple[Decimal, Decimal]:
    equity = enterprise_value + i.cash + i.non_operating_assets - i.debt - i.minority_interest
    return equity, equity / i.shares


def _check(i: FairValueInputs, wacc: Decimal) -> None:
    if i.shares <= 0:
        raise ValuationSkipped("No share count was reported, so value per share can't be computed.")
    if i.stable_growth >= wacc:
        raise InvalidAssumptions(f"Long-run growth ({i.stable_growth:.2%}) must be below the cost of capital ({wacc:.2%}).")
    if i.stable_growth > i.risk_free_rate:
        raise InvalidAssumptions(f"Long-run growth ({i.stable_growth:.2%}) can't exceed the risk-free rate ({i.risk_free_rate:.2%}).")
    if not (1 <= i.high_growth_years <= 10 and 0 <= i.fade_years <= 10):
        raise InvalidAssumptions("Use 1-10 growth years and 0-10 fade years.")


def cost_of_capital(i: FairValueInputs) -> tuple[Decimal, CapitalCost]:
    cost = capital_cost(risk_free=i.risk_free_rate, erp=i.equity_risk_premium, unlevered_beta=i.unlevered_beta,
                        debt_to_capital=i.debt_to_capital, default_spread=i.default_spread, marginal_tax=i.marginal_tax_rate)
    return (i.cost_of_capital_override if i.cost_of_capital_override is not None else cost.cost_of_capital), cost


def dcf_value(i: FairValueInputs, wacc: Decimal) -> dict | None:
    """Cash-flow DCF, or None when reported free cash flow isn't positive (the method doesn't apply)."""
    if i.base_fcf is None or i.base_fcf <= 0:
        return None
    rows, fcf, cumulative = [], i.base_fcf, Decimal("1")
    for year in range(1, i.high_growth_years + i.fade_years + 1):
        growth = _growth(i, year)
        fcf = fcf * (1 + growth)
        cumulative = cumulative * (1 + wacc)
        rows.append({"year": year, "fiscal_year": i.base_year + year, "growth": growth, "fcf": fcf,
                     "discount_factor": 1 / cumulative, "present_value": fcf / cumulative})
    terminal = fcf * (1 + i.stable_growth) / (wacc - i.stable_growth)
    terminal_pv = terminal / cumulative
    explicit = sum((r["present_value"] for r in rows), Decimal("0"))
    enterprise = explicit + terminal_pv
    equity, per_share = _equity_per_share(i, enterprise)
    return {
        "projection": [{k: (_q(v, MONEY) if k in {"fcf", "present_value"} else _q(v) if isinstance(v, Decimal) else v)
                        for k, v in r.items()} for r in rows],
        "terminal_value": _q(terminal, MONEY), "terminal_present_value": _q(terminal_pv, MONEY),
        "terminal_share": _q(terminal_pv / enterprise) if enterprise else Decimal("0"),
        "present_value_of_fcf": _q(explicit, MONEY), "enterprise_value": _q(enterprise, MONEY),
        "equity_value": _q(equity, MONEY), "value_per_share": _q(per_share, MONEY),
    }


def epv_value(i: FairValueInputs, wacc: Decimal) -> dict | None:
    """Earnings power value, or None when normalised operating income isn't positive."""
    if i.normalised_operating_income is None or i.normalised_operating_income <= 0:
        return None
    nopat = i.normalised_operating_income * (1 - i.tax_rate)
    enterprise = nopat / wacc
    equity, per_share = _equity_per_share(i, enterprise)
    return {"normalised_after_tax_operating_income": _q(nopat, MONEY), "enterprise_value": _q(enterprise, MONEY),
            "equity_value": _q(equity, MONEY), "value_per_share": _q(per_share, MONEY)}


def value(i: FairValueInputs, *, with_sensitivity: bool = True) -> dict:
    with localcontext() as context:
        context.prec = 34
        wacc, cost = cost_of_capital(i)
        _check(i, wacc)
        dcf, epv = dcf_value(i, wacc), epv_value(i, wacc)
        methods = {name: Decimal(result["value_per_share"]) for name, result in (("dcf", dcf), ("epv", epv)) if result}
        if not methods:
            raise ValuationSkipped("Neither free cash flow nor normalised operating income is positive, so neither method applies.")
        fair = sum(methods.values(), Decimal("0")) / len(methods)
        warnings = []
        if dcf is None:
            warnings.append("Reported free cash flow isn't positive over the last three years, so the cash-flow DCF doesn't apply; fair value rests on earnings power alone.")
        if epv is None:
            warnings.append("Normalised operating income isn't positive, so earnings power value doesn't apply.")
        if dcf and Decimal(dcf["terminal_share"]) > Decimal("0.8"):
            warnings.append(f"The terminal value is {Decimal(dcf['terminal_share']):.0%} of the DCF value, so the long-run assumptions dominate it.")
        if len(methods) == 2:
            spread = max(methods.values()) / min(methods.values()) - 1 if min(methods.values()) > 0 else None
            if spread is not None and spread > 1:
                warnings.append("The two methods differ by more than 2x: most of the DCF value comes from expected growth.")
        result = {
            "calculation_version": CALCULATION_VERSION,
            "inputs": i.to_json(),
            "cost_of_capital": {"levered_beta": _q(cost.levered_beta), "cost_of_equity": _q(cost.cost_of_equity),
                                "pre_tax_cost_of_debt": _q(cost.pre_tax_cost_of_debt),
                                "after_tax_cost_of_debt": _q(cost.after_tax_cost_of_debt), "cost_of_capital": _q(wacc)},
            "dcf": dcf, "epv": epv,
            "fair_value": _q(fair, MONEY), "range_low": _q(min(methods.values()), MONEY), "range_high": _q(max(methods.values()), MONEY),
            "methods_used": sorted(methods),
            "warnings": warnings,
        }
        if with_sensitivity and dcf:
            result["sensitivity"] = sensitivity(i, wacc)
        return _stringify(result)


def sensitivity(i: FairValueInputs, wacc: Decimal) -> dict:
    """DCF value per share as the cost of capital and the initial growth rate move. None where the model breaks."""
    grid = []
    for wd in SENSITIVITY_WACC_DELTAS:
        row = []
        for gd in SENSITIVITY_GROWTH_DELTAS:
            trial = replace(i, cost_of_capital_override=wacc + wd, initial_growth=max(i.initial_growth + gd, Decimal("0")))
            try:
                dcf = dcf_value(trial, wacc + wd) if i.stable_growth < wacc + wd else None
                row.append(Decimal(dcf["value_per_share"]) if dcf else None)
            except (InvalidAssumptions, ValuationSkipped):
                row.append(None)
        grid.append(row)
    return {"cost_of_capital_deltas": SENSITIVITY_WACC_DELTAS, "growth_deltas": SENSITIVITY_GROWTH_DELTAS, "value_per_share": grid}


def implied_growth(i: FairValueInputs, price: Decimal) -> Decimal | None:
    """The initial growth rate at which the cash-flow DCF equals `price` (reverse DCF). None if out of 0-60%."""
    with localcontext() as context:
        context.prec = 34
        wacc, _ = cost_of_capital(i)

        def per_share(growth: Decimal) -> Decimal | None:
            dcf = dcf_value(replace(i, initial_growth=growth), wacc)
            return Decimal(dcf["value_per_share"]) if dcf else None

        lo, hi = Decimal("0"), Decimal("0.60")
        v_lo, v_hi = per_share(lo), per_share(hi)
        if v_lo is None or v_hi is None or not v_lo <= price <= v_hi:
            return None
        for _ in range(40):
            mid = (lo + hi) / 2
            if per_share(mid) < price:
                lo = mid
            else:
                hi = mid
        return _q((lo + hi) / 2, Decimal("0.0001"))


def apply_overrides(inputs: FairValueInputs, overrides: dict) -> FairValueInputs:
    clean = {k: v for k, v in overrides.items() if v is not None}
    sources = dict(inputs.sources)
    for key in clean:
        sources[key] = "what-if (user override)"
    return replace(inputs, **clean, sources=sources)
