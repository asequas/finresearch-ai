"""Extract annual reported values from SEC XBRL companyfacts (pure, no I/O).

Rules (ADR 0005):
- Only facts from 10-K / 10-K/A with a ~1-year duration (flows) or the period-end
  instant (balances).
- A fact's `fy` is the fiscal year of the *filing*, not of the period (a FY2024
  10-K also reports FY2023 comparatives), so periods are keyed by end date.
- When several filings report the same period, the latest-filed value wins
  (restatements).
- Concepts are tried in order; the first one with a value for that period wins.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}

FLOW_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    "cost_of_revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capital_expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "research_and_development": (
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
    # Inputs to the DCF (ADR 0010).
    "depreciation_amortization": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ),
    "income_tax_expense": ("IncomeTaxExpenseBenefit",),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ),
    "share_based_compensation": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
    "eps": ("EarningsPerShareDiluted",),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}

INSTANT_CONCEPTS: dict[str, tuple[str, ...]] = {
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "debt": ("LongTermDebt", "LongTermDebtNoncurrent"),
    # Inputs to the DCF's equity bridge (ADR 0010).
    "short_term_investments": ("ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"),
    "lease_liabilities": ("OperatingLeaseLiability",),
    "minority_interest": ("MinorityInterest",),
}

UNIT_FOR_FIELD = {"eps": "USD/shares", "diluted_shares": "shares"}


@dataclass
class ExtractedPeriod:
    fiscal_year: int
    period_end: date
    values: dict[str, Decimal] = field(default_factory=dict)
    provenance: dict[str, dict] = field(default_factory=dict)


@dataclass
class Extraction:
    periods: list[ExtractedPeriod]
    missing: dict[str, list[int]]  # field -> fiscal years with no value
    currency: str = "USD"


class UnsupportedFinancialsError(ValueError):
    pass


def fiscal_year_for(period_end: date) -> int:
    """52/53-week years ending in the first days of January belong to the prior fiscal year."""
    if period_end.month == 1 and period_end.day <= 7:
        return period_end.year - 1
    return period_end.year


def _facts(company_facts: dict, concept: str, unit: str) -> list[dict]:
    node = company_facts.get("facts", {}).get("us-gaap", {}).get(concept)
    if not node:
        return []
    return node.get("units", {}).get(unit, [])


def _is_annual_flow(fact: dict) -> bool:
    if fact.get("form") not in ANNUAL_FORMS or "start" not in fact:
        return False
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return 350 <= days <= 380


def _is_annual_instant(fact: dict) -> bool:
    return fact.get("form") in ANNUAL_FORMS and "start" not in fact


def _latest_by_end(facts: list[dict]) -> dict[date, dict]:
    chosen: dict[date, dict] = {}
    for fact in facts:
        end = date.fromisoformat(fact["end"])
        current = chosen.get(end)
        if current is None or (fact.get("filed", ""), fact.get("accn", "")) > (
            current.get("filed", ""),
            current.get("accn", ""),
        ):
            chosen[end] = fact
    return chosen


def _provenance(concept: str, fact: dict, unit: str) -> dict:
    return {
        "concept": f"us-gaap:{concept}",
        "accession": fact.get("accn"),
        "form": fact.get("form"),
        "filed": fact.get("filed"),
        "unit": unit,
        "period_start": fact.get("start"),
        "period_end": fact.get("end"),
    }


def extract_annual_periods(company_facts: dict, years: int = 5) -> Extraction:
    revenue_ends: set[date] = set()
    for concept in FLOW_CONCEPTS["revenue"] + FLOW_CONCEPTS["net_income"]:
        revenue_ends |= set(_latest_by_end([f for f in _facts(company_facts, concept, "USD") if _is_annual_flow(f)]))
    if not revenue_ends:
        has_other_currency = any(
            unit != "USD"
            for concept in FLOW_CONCEPTS["revenue"]
            for unit in company_facts.get("facts", {}).get("us-gaap", {}).get(concept, {}).get("units", {})
        )
        if has_other_currency:
            raise UnsupportedFinancialsError("This company reports in a currency other than USD (not supported in v1).")
        raise UnsupportedFinancialsError("No annual (10-K) revenue or net income found in SEC XBRL data.")

    # Keep the latest `years` distinct fiscal years.
    by_year: dict[int, date] = {}
    for end in sorted(revenue_ends):
        by_year[fiscal_year_for(end)] = end
    selected = sorted(by_year.items())[-years:]
    periods = [ExtractedPeriod(fiscal_year=year, period_end=end) for year, end in selected]

    for field_name, concepts in FLOW_CONCEPTS.items():
        unit = UNIT_FOR_FIELD.get(field_name, "USD")
        for period in periods:
            for concept in concepts:
                fact = _latest_by_end([f for f in _facts(company_facts, concept, unit) if _is_annual_flow(f)]).get(
                    period.period_end
                )
                if fact is not None:
                    period.values[field_name] = Decimal(str(fact["val"]))
                    period.provenance[field_name] = _provenance(concept, fact, unit)
                    break

    for field_name, concepts in INSTANT_CONCEPTS.items():
        for period in periods:
            for concept in concepts:
                fact = _latest_by_end([f for f in _facts(company_facts, concept, "USD") if _is_annual_instant(f)]).get(
                    period.period_end
                )
                if fact is not None:
                    period.values[field_name] = Decimal(str(fact["val"]))
                    period.provenance[field_name] = _provenance(concept, fact, "USD")
                    break

    all_fields = list(FLOW_CONCEPTS) + list(INSTANT_CONCEPTS)
    missing = {
        name: [p.fiscal_year for p in periods if name not in p.values]
        for name in all_fields
        if any(name not in p.values for p in periods)
    }
    return Extraction(periods=periods, missing=missing)
