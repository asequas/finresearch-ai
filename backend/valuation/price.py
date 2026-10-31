"""Current share price from Cboe's free delayed quotes (ADR 0012): no key, ~15 minutes delayed.

Cboe's website terms allow personal, non-commercial use; a product sold to customers needs a licensed feed. The
source is a setting (`price_source`), so a licensed provider can replace this without touching the valuation. The
quote is cached for 15 minutes; any failure returns None and the reader can still type a price.
"""
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)

CBOE_QUOTE = "https://cdn-api.cboe.com/api/global/delayed_quotes/quotes/{symbol}.json"
CBOE_SOURCE = "Cboe delayed quote (about 15 minutes; personal/demo use)"
CACHE_SECONDS = 15 * 60


@dataclass(frozen=True)
class MarketPrice:
    price: Decimal
    as_of: datetime  # time of the last trade in the quote (exchange time, US Eastern)
    source: str


def parse_cboe_quote(payload: dict) -> MarketPrice | None:
    data = payload.get("data") or {}
    price = data.get("current_price") or data.get("close")
    stamp = data.get("last_trade_time")
    if not price or not stamp:
        return None
    return MarketPrice(Decimal(str(price)).quantize(Decimal("0.01")), datetime.fromisoformat(stamp), CBOE_SOURCE)


def _fetch(symbol: str) -> dict:
    import httpx

    response = httpx.get(CBOE_QUOTE.format(symbol=symbol), timeout=10, follow_redirects=True,
                         headers={"User-Agent": "FinResearch AI (personal research)"})
    response.raise_for_status()
    return response.json()


def latest_price(ticker: str, cache_dir: str | Path, *, source: str = "cboe_delayed",
                 fetch: Callable[[str], dict] = _fetch, now: float | None = None) -> MarketPrice | None:
    if source != "cboe_delayed":
        return None
    symbol = ticker.upper().replace(".", "_")
    now = now if now is not None else time.time()
    cache = Path(cache_dir) / "prices" / f"{symbol}.json"
    if cache.exists():
        cached = json.loads(cache.read_text())
        if now - cached["fetched_at"] < CACHE_SECONDS:
            return parse_cboe_quote(cached["payload"])
    try:
        payload = fetch(symbol)
        quote = parse_cboe_quote(payload)
        if quote is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"fetched_at": now, "payload": payload}))
        return quote
    except Exception:
        logger.warning("could not fetch a delayed quote for %s", ticker, exc_info=True)
        return None
