"""Default DCF assumptions from a company's filings and the reference data, each with its source (ADR 0010)."""
from decimal import Decimal

from backend.analysis.metrics import FinancialPeriod
from backend.valuation.dcf import (
    DcfInputs,
    ValuationSkipped,
    adjusted_operating_income,
    capital_cost,
    effective_tax_rate,
    fundamentals,
    research_asset,
)
from backend.valuation.industries import industry_for_sic
from backend.valuation.market import RiskFreeRate
from backend.valuation.reference import (
    ERP,
    ERP_AS_OF,
    DEFAULT_RD_LIFE,
    INDUSTRY_DATA_DATE,
    LONG_HIGH_GROWTH_YEARS,
    MARGINAL_TAX_RATE,
    RATINGS_AS_OF,
    RD_LIFE,
    RD_MATERIALITY,
    STABLE_ROC_CAP,
    STRONG_ADVANTAGE_SPREAD,
    industries,
    synthetic_rating,
)

HIGH_GROWTH_YEARS = 5
TRANSITION_YEARS = 5
DEFAULT_STABLE_GROWTH = Decimal("0.03")


def default_inputs(
    periods: list[FinancialPeriod], *, shares: Decimal | None, sic: str | None, risk_free: RiskFreeRate | None,
) -> tuple[DcfInputs, list[str]]:
    """Build the base-case inputs. Raises ValuationSkipped with a reader-facing reason when a DCF can't be done."""
    if risk_free is None:
        raise ValuationSkipped("The risk-free rate (US Treasury 10-year yield) couldn't be fetched and none is cached.")
    periods = sorted(periods, key=lambda p: p.fiscal_year)
    if not periods:
        raise ValuationSkipped("No reported financials to value.")
    base = periods[-1]
    fy = f"FY{base.fiscal_year}"
    if base.operating_income is None or base.operating_income <= 0:
        raise ValuationSkipped(f"Operating income in {fy} is missing or negative, so free cash flow to the firm can't be projected from it.")
    if not shares or shares <= 0:
        raise ValuationSkipped(f"No diluted share count was reported for {fy}.")

    notes: list[str] = []
    tax, tax_source = effective_tax_rate(base, MARGINAL_TAX_RATE)
    match = industry_for_sic(sic)
    industry = industries()[match.industry]
    if match.fallback:
        notes.append(f"SIC {sic or 'unknown'} has no industry mapping, so market-wide beta and debt ratio are used.")

    # R&D is investment, not an expense, when it is material (Damodaran): capitalise it over the industry's life.
    research = None
    if base.research_and_development and base.revenue and base.research_and_development / base.revenue >= RD_MATERIALITY:
        life = RD_LIFE.get(industry.name, DEFAULT_RD_LIFE)
        research = research_asset(periods, life)
        if research and research.estimated_years:
            notes.append(f"R&D before FY{min(research.spend)} isn't in our data; assumed equal to the earliest year for amortisation.")
    base_ebit = adjusted_operating_income(base, research)
    growth = fundamentals(periods, MARGINAL_TAX_RATE, research)
    notes += growth.notes

    rating = synthetic_rating(base.operating_income, base.interest_expense, base.revenue)
    rf = risk_free.rate
    if risk_free.stale:
        notes.append(f"The Treasury yield couldn't be refreshed; using the last cached value from {risk_free.as_of}.")
    stable_growth = min(DEFAULT_STABLE_GROWTH, rf)
    high_cost = capital_cost(risk_free=rf, erp=ERP, unlevered_beta=industry.unlevered_beta_cash_corrected,
                             debt_to_capital=industry.debt_to_capital, default_spread=rating.spread,
                             marginal_tax=MARGINAL_TAX_RATE).cost_of_capital
    stable_cost = capital_cost(risk_free=rf, erp=ERP, unlevered_beta=None, levered_beta=Decimal("1.0"),
                               debt_to_capital=industry.debt_to_capital, default_spread=rating.spread,
                               marginal_tax=MARGINAL_TAX_RATE).cost_of_capital

    # Reinvestment during high growth = growth / ROC. Without a usable ROC, assume no excess returns (ROC = cost of capital).
    roc = growth.return_on_capital
    if roc is None or roc <= 0:
        roc = high_cost
        notes.append("Return on capital couldn't be measured, so new investment is assumed to earn its cost of capital.")

    # Competitive advantage (ADR 0011): a wide, measured edge lasts longer and fades rather than vanishing.
    spread = roc - high_cost
    high_years = LONG_HIGH_GROWTH_YEARS if spread >= STRONG_ADVANTAGE_SPREAD else HIGH_GROWTH_YEARS
    stable_roc = None
    stable_roc_source = "= stable cost of capital (no excess returns forever)"
    if roc > stable_cost:
        stable_roc = min(stable_cost + (roc - stable_cost) / 2, STABLE_ROC_CAP)
        stable_roc_source = (f"midway between return on capital ({roc:.1%}) and stable cost of capital ({stable_cost:.1%}), "
                             f"capped at {STABLE_ROC_CAP:.0%}: the advantage fades but persists")

    years = f"FY{growth.years[0]}-FY{growth.years[-1]}" if growth.years else fy
    industry_source = f"Damodaran US industry data ({INDUSTRY_DATA_DATE:%b %Y}): {industry.name}"
    coverage = f"interest coverage {rating.coverage:.1f}x" if rating.coverage is not None else "no interest expense"
    sources = {
        "base_ebit": (f"Operating income, {fy} (SEC XBRL), + R&D {research.life}-year capitalisation adjustment"
                      if research else f"Operating income, {fy} (SEC XBRL)"),
        "effective_tax_rate": tax_source,
        "marginal_tax_rate": "US federal 21% + state (Damodaran's US marginal rate)",
        "high_growth": f"{growth.method}, {years}",
        "high_growth_years": (f"{LONG_HIGH_GROWTH_YEARS}: return on capital beats the cost of capital by "
                              f"{spread:.0%} points (a lasting advantage)" if high_years == LONG_HIGH_GROWTH_YEARS else "default"),
        "stable_return_on_capital": stable_roc_source,
        "transition_years": "default (linear fade to stable growth)",
        "return_on_capital": (f"after-tax operating income ÷ invested capital{' (incl. research asset)' if research else ''}, {fy}"
                              if growth.return_on_capital else "= cost of capital"),
        "stable_growth": f"default {DEFAULT_STABLE_GROWTH:.0%}, capped at the risk-free rate",
        "risk_free_rate": f"US Treasury 10-year par yield, {risk_free.as_of:%b %d, %Y}",
        "equity_risk_premium": f"Damodaran implied ERP, {ERP_AS_OF:%b %d, %Y}",
        "unlevered_beta": f"{industry_source} (unlevered, cash-corrected, {industry.firms} firms)",
        "debt_to_capital": f"{industry_source} (market D/E {industry.de_ratio:.2f})",
        "default_spread": f"synthetic rating {rating.rating} from {coverage} (Damodaran, {RATINGS_AS_OF:%b %Y})",
        "stable_beta": "default: mature firms move towards the market beta of 1",
        "cash": f"Cash and equivalents, {fy}",
        "non_operating_assets": f"Short-term investments, {fy}",
        "debt": f"Long-term debt, {fy}",
        "lease_liabilities": "not subtracted: operating lease costs are already deducted in operating income (ASC 842)",
        "industry": industry.name,
        "minority_interest": f"Minority interest, {fy}",
        "shares": f"Diluted weighted-average shares, {fy}",
    }
    inputs = DcfInputs(
        base_year=base.fiscal_year, base_ebit=base_ebit, effective_tax_rate=tax,
        marginal_tax_rate=MARGINAL_TAX_RATE, high_growth=growth.growth, high_growth_years=high_years,
        transition_years=TRANSITION_YEARS, return_on_capital=roc, stable_growth=stable_growth, risk_free_rate=rf,
        stable_return_on_capital=stable_roc,
        equity_risk_premium=ERP, unlevered_beta=industry.unlevered_beta_cash_corrected,
        debt_to_capital=industry.debt_to_capital, default_spread=rating.spread,
        cash=base.cash or Decimal("0"), non_operating_assets=base.short_term_investments or Decimal("0"),
        debt=base.debt or Decimal("0"), lease_liabilities=Decimal("0"),
        minority_interest=base.minority_interest or Decimal("0"), shares=shares, sources=sources,
    )
    if base.debt is None:
        notes.append(f"No long-term debt reported for {fy}; treated as zero.")
    return inputs, notes
