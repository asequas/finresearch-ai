"""Valuation reference data: Damodaran's industry table, synthetic ratings and the SIC mapping (ADR 0010)."""
from decimal import Decimal

import pytest

from backend.valuation.industries import industry_for_sic
from backend.valuation.reference import FALLBACK_INDUSTRY, industries, synthetic_rating


def test_industry_table_loads_with_decimal_values():
    table = industries()
    assert len(table) == 96
    software = table["Software (System & Application)"]
    assert isinstance(software.unlevered_beta, Decimal) and software.firms > 100
    assert Decimal("0") < software.debt_to_capital < Decimal("1")
    assert FALLBACK_INDUSTRY in table


@pytest.mark.parametrize(("ticker", "sic", "industry"), [
    ("MSFT", "7372", "Software (System & Application)"),
    ("AAPL", "3571", "Computers/Peripherals"),
    ("NVDA", "3674", "Semiconductor"),
    ("COST", "5331", "Retail (General)"),
    ("WMT", "5331", "Retail (General)"),
    ("AMZN", "5961", "Retail (General)"),
])
def test_sic_codes_of_companies_we_have_researched(ticker, sic, industry):
    match = industry_for_sic(sic)
    assert (match.industry, match.fallback) == (industry, False), ticker


def test_narrowest_range_wins_and_unknown_codes_fall_back():
    assert industry_for_sic("1531").industry == "Homebuilding"  # inside Engineering/Construction 1500-1799
    assert industry_for_sic("3714").industry == "Auto Parts"  # inside Auto & Truck 3713-3716
    unknown = industry_for_sic("9999")
    assert (unknown.industry, unknown.fallback) == (FALLBACK_INDUSTRY, True)
    assert industry_for_sic(None).fallback is True


def test_every_mapped_industry_exists_in_the_table():
    from backend.valuation.industries import _SIC_MAP

    assert {name for _, _, name in _SIC_MAP} <= set(industries())


@pytest.mark.parametrize(("ebit", "interest", "revenue", "rating", "spread", "table"), [
    ("1000", "50", "10e9", "Aaa/AAA", "0.0040", "large"),   # coverage 20
    ("1000", "300", "10e9", "A3/A-", "0.0089", "large"),    # 3.33
    ("1000", "300", "1e9", "Ba2/BB", "0.0184", "small"),    # same coverage, small-firm table
    ("1000", "2000", "10e9", "C2/C", "0.1600", "large"),    # 0.5
    ("-50", "10", "10e9", "D2/D", "0.1900", "large"),       # operating loss
    ("1000", "0", "10e9", "Aaa/AAA", "0.0040", "large"),    # no interest expense
])
def test_synthetic_rating_from_interest_coverage(ebit, interest, revenue, rating, spread, table):
    result = synthetic_rating(Decimal(ebit), Decimal(interest), Decimal(revenue))
    assert (result.rating, result.spread, result.table) == (rating, Decimal(spread), table)
