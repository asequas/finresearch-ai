"""Risk-free rate from the Treasury yield-curve CSV, cached daily, never invented (ADR 0010)."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.valuation.market import latest_risk_free_rate, parse_treasury_csv

FIXTURE = (Path(__file__).parents[1] / "fixtures" / "treasury_202610.csv").read_text()


def test_parses_the_ten_year_column_newest_first():
    rows = parse_treasury_csv(FIXTURE)
    assert rows[0] == (date(2026, 10, 30), Decimal("0.0494"))
    assert rows[-1][0] == date(2026, 10, 28)


def test_fetches_once_a_day_then_serves_the_cache(tmp_path):
    calls = []

    def fetch(month):
        calls.append(month)
        return FIXTURE

    first = latest_risk_free_rate(tmp_path, today=date(2026, 10, 31), fetch=fetch)
    second = latest_risk_free_rate(tmp_path, today=date(2026, 10, 31), fetch=fetch)

    assert (first.rate, first.as_of, first.stale) == (Decimal("0.0494"), date(2026, 10, 30), False)
    assert second == first and calls == ["202610"]


def test_an_empty_month_falls_back_to_the_previous_one(tmp_path):
    def fetch(month):
        return "Date,10 Yr\n" if month == "202611" else FIXTURE

    rate = latest_risk_free_rate(tmp_path, today=date(2026, 11, 1), fetch=fetch)
    assert rate.as_of == date(2026, 10, 30)


def test_a_failed_fetch_uses_the_stale_cache_or_returns_nothing(tmp_path):
    latest_risk_free_rate(tmp_path, today=date(2026, 10, 31), fetch=lambda m: FIXTURE)

    def down(month):
        raise ConnectionError("treasury.gov unreachable")

    stale = latest_risk_free_rate(tmp_path, today=date(2026, 11, 2), fetch=down)
    assert (stale.rate, stale.stale) == (Decimal("0.0494"), True)
    assert latest_risk_free_rate(tmp_path / "empty", today=date(2026, 11, 2), fetch=down) is None
