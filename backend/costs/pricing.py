"""Gemini list prices, per 1M tokens, in USD (ADR 0009).

Source: https://ai.google.dev/gemini-api/docs/pricing, checked 2026-10-31 (standard, not Batch). Prices carry the
date they take effect, so a call is always priced at the rate in force when it was made. Thinking tokens are billed
as output; implicitly cached input is billed at the cached rate.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal

PRICING_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICING_CHECKED = date(2026, 10, 31)
PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Price:
    input: Decimal
    cached_input: Decimal
    output: Decimal
    effective_from: date = date.min


def _p(inp: str, cached: str, out: str, since: date = date.min) -> Price:
    return Price(Decimal(inp), Decimal(cached), Decimal(out), since)


_FLASH = [_p("0.75", "0.075", "3.75"), _p("1.50", "0.15", "7.50", date(2027, 1, 1))]

PRICES: dict[str, list[Price]] = {
    "gemini-3.6-flash": _FLASH,
    "gemini-3.8-flash": _FLASH,
    "gemini-3.5-flash-lite": [_p("0.30", "0.03", "2.50")],
    # Google says this price changes on 2027-01-01 but hasn't published the new one yet.
    "gemini-3.1-flash-lite": [_p("0.25", "0.025", "1.50")],
    "gemini-embedding-001": [_p("0.15", "0.15", "0")],
}


def canonical_model(model: str) -> str:
    """'models/gemini-3.5-flash-lite' and 'gemini-3.5-flash-lite-001' both price as 'gemini-3.5-flash-lite'."""
    name = model.removeprefix("models/").strip()
    matches = [known for known in PRICES if name == known or name.startswith(f"{known}-")]
    return max(matches, key=len) if matches else name


def price_for(model: str, at: datetime | date) -> Price | None:
    day = at.date() if isinstance(at, datetime) else at
    schedule = PRICES.get(canonical_model(model))
    if not schedule:
        return None
    current = [p for p in schedule if p.effective_from <= day]
    return max(current, key=lambda p: p.effective_from) if current else None


def cost_usd(model: str, at: datetime | date, *, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> Decimal | None:
    """List-price cost of one call, or None when the model isn't in the price table."""
    price = price_for(model, at)
    if price is None:
        return None
    cached = min(max(cached_tokens, 0), max(input_tokens, 0))
    raw = (
        (Decimal(input_tokens - cached) * price.input)
        + (Decimal(cached) * price.cached_input)
        + (Decimal(output_tokens) * price.output)
    ) / PER_MILLION
    return raw.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
