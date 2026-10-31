"""The risk-free rate: the US Treasury 10-year par yield (ADR 0010).

Fetched from treasury.gov's daily yield-curve CSV (free, no key) and cached once a day under the data cache. If the
fetch fails, the last cached rate is used and marked stale; with nothing cached, there is no rate and valuations are
skipped with that reason rather than run on a made-up number.
"""
import csv
import io
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)

TREASURY_CSV = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/{month}"
    "?type=daily_treasury_yield_curve&field_tdr_date_value_month={month}&page&_format=csv"
)
TREASURY_PAGE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"


@dataclass(frozen=True)
class RiskFreeRate:
    rate: Decimal  # e.g. 0.0494
    as_of: date
    source: str
    stale: bool = False  # the fetch failed and an older cached value is being used


def parse_treasury_csv(text: str) -> list[tuple[date, Decimal]]:
    """[(date, 10-year yield as a decimal)], newest first, skipping days without a 10-year quote."""
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        value = (row.get("10 Yr") or "").strip()
        if not value:
            continue
        day = datetime.strptime(row["Date"].strip(), "%m/%d/%Y").date()
        rows.append((day, (Decimal(value) / 100).quantize(Decimal("0.0001"))))
    return sorted(rows, reverse=True)


def _fetch_month(month: str) -> str:
    import httpx

    response = httpx.get(TREASURY_CSV.format(month=month), timeout=15, headers={"User-Agent": "FinResearch AI"})
    response.raise_for_status()
    return response.text


def latest_risk_free_rate(
    cache_dir: str | Path, *, today: date | None = None, fetch: Callable[[str], str] = _fetch_month,
) -> RiskFreeRate | None:
    today = today or date.today()
    cache = Path(cache_dir) / "treasury_10y.json"
    cached = json.loads(cache.read_text()) if cache.exists() else None
    if cached and cached.get("fetched_on") == today.isoformat():
        return RiskFreeRate(Decimal(cached["rate"]), date.fromisoformat(cached["as_of"]), TREASURY_PAGE)

    try:
        # Early in a month the current file may have no rows yet; fall back to last month's.
        for month in (today.strftime("%Y%m"), (today.replace(day=1) - timedelta(days=1)).strftime("%Y%m")):
            rows = parse_treasury_csv(fetch(month))
            if rows:
                as_of, rate = rows[0]
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({"rate": str(rate), "as_of": as_of.isoformat(), "fetched_on": today.isoformat()}))
                return RiskFreeRate(rate, as_of, TREASURY_PAGE)
    except Exception:
        logger.warning("could not fetch the Treasury 10-year yield", exc_info=True)

    if cached:
        return RiskFreeRate(Decimal(cached["rate"]), date.fromisoformat(cached["as_of"]), TREASURY_PAGE, stale=True)
    return None
