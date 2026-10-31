"""Market-wide valuation inputs with their sources and dates (ADR 0010).

Like the LLM price table, every number here is dated so a valuation can say exactly which data it used.
"""
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Damodaran's implied ERP for the S&P 500 (trailing 12-month, adjusted payout), shown on his home page.
ERP = Decimal("0.0420")
ERP_AS_OF = date(2026, 10, 1)
ERP_SOURCE = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm"

# US federal 21% plus a typical state rate; Damodaran's datasets use 25% as the US marginal rate.
MARGINAL_TAX_RATE = Decimal("0.25")

INDUSTRY_DATA_FILE = DATA_DIR / "damodaran_us_industries_2026.csv"
INDUSTRY_DATA_DATE = date(2026, 1, 5)
INDUSTRY_DATA_SOURCE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
RATINGS_SOURCE = "https://pages.stern.nyu.edu/~adamodar/pc/ratings.xls"
RATINGS_AS_OF = date(2026, 1, 1)

FALLBACK_INDUSTRY = "Total Market (without financials)"
# Without a share price, firm size for the ratings table is judged by revenue (Damodaran's cut-off is $5B market cap).
LARGE_FIRM_REVENUE = Decimal("5000000000")


@dataclass(frozen=True)
class Industry:
    name: str
    firms: int
    levered_beta: Decimal
    de_ratio: Decimal
    effective_tax_rate: Decimal
    unlevered_beta: Decimal
    cash_to_firm_value: Decimal
    unlevered_beta_cash_corrected: Decimal

    @property
    def debt_to_capital(self) -> Decimal:
        """D/(D+E) from the industry's market D/E."""
        return self.de_ratio / (1 + self.de_ratio)


@cache
def industries() -> dict[str, Industry]:
    with INDUSTRY_DATA_FILE.open(newline="") as f:
        return {
            row["industry"]: Industry(
                name=row["industry"], firms=int(row["firms"]), levered_beta=Decimal(row["levered_beta"]),
                de_ratio=Decimal(row["de_ratio"]), effective_tax_rate=Decimal(row["effective_tax_rate"]),
                unlevered_beta=Decimal(row["unlevered_beta"]), cash_to_firm_value=Decimal(row["cash_to_firm_value"]),
                unlevered_beta_cash_corrected=Decimal(row["unlevered_beta_cash_corrected"]),
            )
            for row in csv.DictReader(f)
        }


# (coverage greater than or equal to, rating, default spread), highest first. From ratings.xls, January 2026.
_LARGE_FIRMS = [
    ("8.5", "Aaa/AAA", "0.0040"), ("6.5", "Aa2/AA", "0.0055"), ("5.5", "A1/A+", "0.0070"), ("4.25", "A2/A", "0.0078"),
    ("3.0", "A3/A-", "0.0089"), ("2.5", "Baa2/BBB", "0.0111"), ("2.25", "Ba1/BB+", "0.0138"), ("2.0", "Ba2/BB", "0.0184"),
    ("1.75", "B1/B+", "0.0275"), ("1.5", "B2/B", "0.0321"), ("1.25", "B3/B-", "0.0509"), ("0.8", "Caa/CCC", "0.0885"),
    ("0.65", "Ca2/CC", "0.1261"), ("0.2", "C2/C", "0.1600"), ("-100000", "D2/D", "0.1900"),
]
_SMALL_FIRMS = [
    ("12.5", "Aaa/AAA", "0.0040"), ("9.5", "Aa2/AA", "0.0055"), ("7.5", "A1/A+", "0.0070"), ("6.0", "A2/A", "0.0078"),
    ("4.5", "A3/A-", "0.0089"), ("4.0", "Baa2/BBB", "0.0111"), ("3.5", "Ba1/BB+", "0.0138"), ("3.0", "Ba2/BB", "0.0184"),
    ("2.5", "B1/B+", "0.0275"), ("2.0", "B2/B", "0.0321"), ("1.5", "B3/B-", "0.0509"), ("1.25", "Caa/CCC", "0.0885"),
    ("0.8", "Ca2/CC", "0.1261"), ("0.5", "C2/C", "0.1600"), ("-100000", "D2/D", "0.1900"),
]


@dataclass(frozen=True)
class SyntheticRating:
    coverage: Decimal | None
    rating: str
    spread: Decimal
    table: str  # "large" or "small"


def synthetic_rating(ebit: Decimal, interest_expense: Decimal | None, revenue: Decimal | None) -> SyntheticRating:
    """Damodaran's synthetic rating from interest coverage (EBIT / interest expense).

    No interest expense means no meaningful debt burden: the top rating.
    """
    table, name = (_LARGE_FIRMS, "large") if (revenue or 0) >= LARGE_FIRM_REVENUE else (_SMALL_FIRMS, "small")
    if not interest_expense or interest_expense <= 0:
        return SyntheticRating(coverage=None, rating=table[0][1], spread=Decimal(table[0][2]), table=name)
    coverage = ebit / interest_expense
    for floor, rating, spread in table:
        if coverage >= Decimal(floor):
            return SyntheticRating(coverage=coverage, rating=rating, spread=Decimal(spread), table=name)
    floor, rating, spread = table[-1]
    return SyntheticRating(coverage=coverage, rating=rating, spread=Decimal(spread), table=name)

