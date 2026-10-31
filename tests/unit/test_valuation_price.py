"""Delayed share price from Cboe: parsed, cached for 15 minutes, failing safe (ADR 0012). No network in tests."""
from datetime import datetime
from decimal import Decimal

from backend.valuation.price import latest_price, parse_cboe_quote

QUOTE = {"data": {"symbol": "MSFT", "current_price": 522.992, "close": 521.91, "last_trade_time": "2026-10-30T15:59:59"}}


def test_parses_the_delayed_quote():
    quote = parse_cboe_quote(QUOTE)
    assert quote.price == Decimal("522.99") and quote.as_of == datetime(2026, 10, 30, 15, 59, 59)
    assert "delayed" in quote.source


def test_caches_for_fifteen_minutes_and_fails_safe(tmp_path):
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return QUOTE

    assert latest_price("msft", tmp_path, fetch=fetch, now=1000).price == Decimal("522.99")
    assert latest_price("MSFT", tmp_path, fetch=fetch, now=1000 + 600).price == Decimal("522.99")
    assert calls == ["MSFT"]  # the second read came from the cache

    def down(symbol):
        raise ConnectionError("cboe unreachable")

    assert latest_price("MSFT", tmp_path, fetch=down, now=1000 + 3600) is None
    assert latest_price("MSFT", tmp_path, source="none", fetch=fetch) is None
