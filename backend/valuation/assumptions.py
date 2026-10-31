"""Default fair-value inputs from a company's filings and dated reference data, each with its source (ADR 0012)."""
from decimal import Decimal

from backend.analysis.metrics import FinancialPeriod
from backend.valuation.fair_value import FairValueInputs, ValuationSkipped
from backend.valuation.industries import industry_for_sic
from backend.valuation.market import RiskFreeRate
from backend.valuation.reference import (
    ERP,
    ERP_AS_OF,
    INDUSTRY_DATA_DATE,
    MARGINAL_TAX_RATE,
    RATINGS_AS_OF,
    industries,
    synthetic_rating,
)

GROWTH_YEARS = 5
FADE_YEARS = 5
LONG_RUN_GROWTH = Decimal("0.025")  # roughly long-run nominal US growth; never above the risk-free rate
GROWTH_CAP = Decimal("0.20")
FCF_YEARS = 3


def _tax_rate(p: FinancialPeriod) -> Decimal | None:
    if p.income_tax_expense is None or not p.pretax_income or p.pretax_income <= 0:
        return None
    return min(max(p.income_tax_expense / p.pretax_income, Decimal("0")), MARGINAL_TAX_RATE)


def default_inputs(
    periods: list[FinancialPeriod], *, shares: Decimal | None, sic: str | None, risk_free: RiskFreeRate | None,
) -> tuple[FairValueInputs, list[str]]:
    """Build the base-case inputs. Raises ValuationSkipped with a reader-facing reason when nothing can be valued."""
    if risk_free is None:
        raise ValuationSkipped("The risk-free rate (US Treasury 10-year yield) couldn't be fetched and none is cached.")
    periods = sorted(periods, key=lambda p: p.fiscal_year)
    if not periods:
        raise ValuationSkipped("No reported financials to value.")
    base = periods[-1]
    fy = f"FY{base.fiscal_year}"
    if not shares or shares <= 0:
        raise ValuationSkipped(f"No diluted share count was reported for {fy}.")
    notes: list[str] = []

    # Tax: the average effective rate across the years we hold, capped at the marginal rate.
    rates = [r for r in (_tax_rate(p) for p in periods) if r is not None]
    tax = sum(rates, Decimal("0")) / len(rates) if rates else MARGINAL_TAX_RATE
    tax_source = (f"average effective tax rate, FY{periods[0].fiscal_year}-{fy} (income tax ÷ pre-tax income)"
                  if rates else "US marginal rate (effective rate not reported)")

    # Reported free cash flow to the firm, per year.
    history = []
    for p in periods:
        if p.operating_cash_flow is None or p.capital_expenditure is None:
            continue
        p_tax = _tax_rate(p) if _tax_rate(p) is not None else tax
        interest = (p.interest_expense or Decimal("0")) * (1 - p_tax)
        sbc = p.share_based_compensation or Decimal("0")
        fcf = p.operating_cash_flow + interest - p.capital_expenditure - sbc
        history.append({"fiscal_year": p.fiscal_year, "operating_cash_flow": p.operating_cash_flow,
                        "after_tax_interest": interest, "capital_expenditure": p.capital_expenditure,
                        "share_based_compensation": sbc, "fcf": fcf})
        if p.share_based_compensation is None:
            notes.append(f"FY{p.fiscal_year}: stock-based compensation not reported, so none is deducted.")
    recent = history[-FCF_YEARS:]
    base_fcf = sum((h["fcf"] for h in recent), Decimal("0")) / len(recent) if recent else None
    if not recent:
        notes.append("Cash from operations or capex isn't reported, so the cash-flow DCF can't be computed.")

    # Growth: the revenue record (compound annual growth), capped, then faded to the long-run rate.
    revenues = [p for p in periods if p.revenue and p.revenue > 0]
    growth = Decimal("0")
    growth_source = "no usable revenue history; 0% assumed"
    if len(revenues) >= 2:
        span = revenues[-1].fiscal_year - revenues[0].fiscal_year
        raw = (revenues[-1].revenue / revenues[0].revenue) ** (Decimal(1) / Decimal(span)) - 1
        growth = min(max(raw, Decimal("0")), GROWTH_CAP)
        growth_source = f"revenue growth FY{revenues[0].fiscal_year}-{fy}: {raw:.1%} a year"
        if raw > GROWTH_CAP:
            growth_source += f", capped at {GROWTH_CAP:.0%}"
            notes.append(f"Revenue grew {raw:.0%} a year; growth that fast rarely lasts, so the forecast uses {GROWTH_CAP:.0%}.")
        elif raw < 0:
            growth_source += ", floored at 0%"

    # Earnings power: average operating margin applied to the latest revenue.
    margins = [p.operating_income / p.revenue for p in periods if p.operating_income is not None and p.revenue and p.revenue > 0]
    normalised = None
    if margins and base.revenue:
        margin = sum(margins, Decimal("0")) / len(margins)
        normalised = margin * base.revenue if margin > 0 else None

    match = industry_for_sic(sic)
    industry = industries()[match.industry]
    if match.fallback:
        notes.append(f"SIC {sic or 'unknown'} has no industry mapping, so market-wide beta and debt ratio are used.")
    rating = synthetic_rating(base.operating_income or Decimal("0"), base.interest_expense, base.revenue)
    if risk_free.stale:
        notes.append(f"The Treasury yield couldn't be refreshed; using the last cached value from {risk_free.as_of}.")
    long_run = min(LONG_RUN_GROWTH, risk_free.rate)
    industry_source = f"Damodaran US industry data ({INDUSTRY_DATA_DATE:%b %Y}): {industry.name}"
    coverage = f"interest coverage {rating.coverage:.1f}x" if rating.coverage is not None else "no interest expense"

    sources = {
        "base_fcf": (f"average reported free cash flow to the firm, FY{recent[0]['fiscal_year']}-{fy}: cash from operations "
                     "+ after-tax interest − capex − stock-based compensation") if recent else "not available",
        "initial_growth": growth_source,
        "high_growth_years": "default",
        "fade_years": "default (straight line to long-run growth)",
        "stable_growth": f"long-run US nominal growth, {LONG_RUN_GROWTH:.1%} (never above the risk-free rate)",
        "normalised_operating_income": (f"average operating margin {sum(margins, Decimal('0')) / len(margins):.1%} "
                                        f"× {fy} revenue") if normalised else "not available (losses)",
        "tax_rate": tax_source,
        "risk_free_rate": f"US Treasury 10-year par yield, {risk_free.as_of:%b %d, %Y}",
        "equity_risk_premium": f"Damodaran implied ERP, {ERP_AS_OF:%b %d, %Y}",
        "unlevered_beta": f"{industry_source} (unlevered, cash-corrected, {industry.firms} firms)",
        "debt_to_capital": f"{industry_source} (market D/E {industry.de_ratio:.2f})",
        "default_spread": f"synthetic rating {rating.rating} from {coverage} (Damodaran, {RATINGS_AS_OF:%b %Y})",
        "marginal_tax_rate": "US federal 21% + state",
        "cash": f"Cash and equivalents, {fy}",
        "non_operating_assets": f"Short-term investments, {fy}",
        "debt": f"Long-term debt, {fy}",
        "minority_interest": f"Minority interest, {fy}",
        "shares": f"Diluted weighted-average shares, {fy}",
        "industry": industry.name,
    }
    if base.debt is None:
        notes.append(f"No long-term debt reported for {fy}; treated as zero.")
    inputs = FairValueInputs(
        base_year=base.fiscal_year, base_fcf=base_fcf, initial_growth=growth, high_growth_years=GROWTH_YEARS,
        fade_years=FADE_YEARS, stable_growth=long_run, normalised_operating_income=normalised, tax_rate=tax,
        risk_free_rate=risk_free.rate, equity_risk_premium=ERP, unlevered_beta=industry.unlevered_beta_cash_corrected,
        debt_to_capital=industry.debt_to_capital, default_spread=rating.spread, marginal_tax_rate=MARGINAL_TAX_RATE,
        cash=base.cash or Decimal("0"), non_operating_assets=base.short_term_investments or Decimal("0"),
        debt=base.debt or Decimal("0"), minority_interest=base.minority_interest or Decimal("0"), shares=shares,
        sources=sources, history=history,
    )
    return inputs, notes
