"""SEC EDGAR client: declared User-Agent, fair-access rate limit, on-disk cache.

https://www.sec.gov/os/accessing-edgar-data asks for <= 10 requests/second and a
User-Agent that identifies the requester with a contact email.
"""
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from backend.pipeline.base import PermanentError, RetryableError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"

HOUR = 3600


class _RateLimiter:
    """Process-wide: at most `rate` requests per second across all threads."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        if slot > now:
            time.sleep(slot - now)


_limiter = _RateLimiter(rate=8)


@dataclass(frozen=True)
class CompanyRecord:
    cik: str  # zero-padded to 10 digits
    ticker: str
    name: str
    sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None
    exchange: str | None


@dataclass(frozen=True)
class Filing:
    cik: str
    accession_number: str
    form: str
    filed: date
    report_date: date | None
    primary_document: str
    description: str | None

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(
            cik=int(self.cik), accession=self.accession_number.replace("-", ""), document=self.primary_document
        )


def is_financial_sector(sic: str | None) -> bool:
    """SIC 6000-6799: banks, insurers, brokers, REITs. Out of scope for v1 metrics."""
    return sic is not None and sic.isdigit() and 6000 <= int(sic) <= 6799


class SecClient:
    def __init__(self, user_agent: str | None, cache_dir: str | Path, http: httpx.Client | None = None):
        if not user_agent or "@" not in user_agent:
            raise PermanentError(
                "SEC_USER_AGENT is not configured. Set it in .env to 'AppName contact@email' "
                "(SEC EDGAR requires a contact email)."
            )
        self.cache_dir = Path(cache_dir) / "sec"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = http or httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    # ---- transport -------------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / hashlib.sha256(url.encode()).hexdigest()

    def fetch(self, url: str, *, max_age_seconds: float | None) -> bytes | None:
        """GET with cache. max_age None = immutable (cache forever). Returns None on 404."""
        path = self._cache_path(url)
        if path.exists() and (max_age_seconds is None or time.time() - path.stat().st_mtime < max_age_seconds):
            return path.read_bytes()

        _limiter.wait()
        try:
            response = self.http.get(url)
        except httpx.TransportError as exc:
            raise RetryableError(f"SEC EDGAR unreachable: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code in (403, 429) or response.status_code >= 500:
            raise RetryableError(f"SEC EDGAR returned {response.status_code} for {url}")
        response.raise_for_status()

        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(path)  # atomic: concurrent workers never read half a file
        return response.content

    def fetch_json(self, url: str, *, max_age_seconds: float | None) -> dict | None:
        raw = self.fetch(url, max_age_seconds=max_age_seconds)
        return None if raw is None else json.loads(raw)

    # ---- domain ----------------------------------------------------------

    def resolve_ticker(self, ticker: str) -> CompanyRecord:
        tickers = self.fetch_json(TICKERS_URL, max_age_seconds=24 * HOUR) or {}
        wanted = {ticker.upper(), ticker.upper().replace(".", "-")}
        match = next((row for row in tickers.values() if row["ticker"].upper() in wanted), None)
        if match is None:
            raise PermanentError(f"Ticker {ticker} was not found in SEC EDGAR's company list.")

        cik = str(match["cik_str"]).zfill(10)
        submissions = self.submissions(cik)
        exchanges = submissions.get("exchanges") or []
        return CompanyRecord(
            cik=cik,
            ticker=ticker.upper(),
            name=submissions.get("name") or match["title"],
            sic=submissions.get("sic") or None,
            sic_description=submissions.get("sicDescription") or None,
            fiscal_year_end=submissions.get("fiscalYearEnd") or None,
            exchange=exchanges[0] if exchanges else None,
        )

    def submissions(self, cik: str) -> dict:
        data = self.fetch_json(SUBMISSIONS_URL.format(cik=cik), max_age_seconds=6 * HOUR)
        if data is None:
            raise PermanentError(f"SEC EDGAR has no filing history for CIK {cik}.")
        return data

    def latest_filings(self, cik: str, form: str, limit: int = 1) -> list[Filing]:
        recent = self.submissions(cik).get("filings", {}).get("recent", {})
        filings = []
        for i, filing_form in enumerate(recent.get("form", [])):
            if filing_form != form:
                continue
            report_date = recent["reportDate"][i]
            filings.append(
                Filing(
                    cik=cik,
                    accession_number=recent["accessionNumber"][i],
                    form=filing_form,
                    filed=date.fromisoformat(recent["filingDate"][i]),
                    report_date=date.fromisoformat(report_date) if report_date else None,
                    primary_document=recent["primaryDocument"][i],
                    description=recent.get("primaryDocDescription", [None] * (i + 1))[i],
                )
            )
            if len(filings) == limit:
                break
        return filings

    def company_facts(self, cik: str) -> dict:
        data = self.fetch_json(COMPANY_FACTS_URL.format(cik=cik), max_age_seconds=6 * HOUR)
        if data is None:
            raise PermanentError("SEC EDGAR has no XBRL financial data for this company.")
        return data

    def filing_document(self, filing: Filing) -> bytes:
        raw = self.fetch(filing.url, max_age_seconds=None)  # filings are immutable
        if raw is None:
            raise PermanentError(f"Filing document {filing.url} is missing on SEC EDGAR.")
        return raw
