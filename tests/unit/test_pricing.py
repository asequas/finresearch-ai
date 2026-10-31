"""List prices and call costs (ADR 0009): Decimal, dated, and per token class."""
from datetime import date
from decimal import Decimal

from backend.costs.pricing import canonical_model, cost_usd, price_for


def test_cost_counts_uncached_input_cached_input_and_output_separately():
    # 100k input of which 40k cached, 10k output (thinking included) on 3.5-flash-lite: $0.30 / $0.03 / $2.50 per 1M.
    cost = cost_usd("gemini-3.5-flash-lite", date(2026, 10, 31), input_tokens=100_000, cached_tokens=40_000, output_tokens=10_000)
    assert cost == Decimal("0.04420000")  # 0.018 + 0.0012 + 0.025


def test_prices_follow_their_effective_date():
    assert price_for("gemini-3.6-flash", date(2026, 12, 31)).input == Decimal("0.75")
    assert price_for("gemini-3.6-flash", date(2027, 1, 1)).input == Decimal("1.50")


def test_model_names_are_normalised_and_unknown_models_are_unpriced():
    assert canonical_model("models/gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"
    assert canonical_model("gemini-3.5-flash-lite-001") == "gemini-3.5-flash-lite"
    assert cost_usd("some-new-model", date(2026, 10, 31), input_tokens=10, output_tokens=10) is None


def test_embeddings_cost_input_only():
    assert cost_usd("gemini-embedding-001", date(2026, 10, 31), input_tokens=1_000_000, output_tokens=0) == Decimal("0.15000000")


def test_cached_tokens_never_exceed_input():
    assert cost_usd("gemini-3.5-flash-lite", date(2026, 10, 31), input_tokens=10, cached_tokens=50, output_tokens=0) == Decimal("0.00000030")
