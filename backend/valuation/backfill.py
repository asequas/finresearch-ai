"""Value research jobs that ran before the DCF existed (ADR 0010).

Run: python -m backend.valuation.backfill [--revalue] [TICKER ...]   (--revalue recomputes existing valuations too)

For each completed job without a valuation it fills in the DCF facts the old snapshots lack (D&A, taxes, short-term
investments, leases, minority interest) from SEC companyfacts, matched by period end. Values already stored are never
changed, so old reports stay reproducible. Then it computes and stores the default valuation. Sources: SEC and
treasury.gov only, never a language model. Prints each result.
"""
import sys

from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models.company import Company
from backend.models.financial_snapshot import VALUATION_MONEY_FIELDS, FinancialSnapshot
from backend.models.research_job import ResearchJob, ResearchJobStatus
from backend.models.valuation import Valuation
from backend.pipeline.research import compute_valuation, save_valuation
from backend.sources.sec import SecClient
from backend.sources.xbrl import extract_annual_periods
from backend.valuation.market import latest_risk_free_rate


def backfill(tickers: list[str] | None = None, *, sec: SecClient | None = None, risk_free=None, revalue: bool = False) -> list[str]:
    sec = sec or SecClient(settings.sec_user_agent, settings.data_cache_dir)
    risk_free = risk_free or latest_risk_free_rate(settings.data_cache_dir)
    lines = []
    with SessionLocal() as session:
        query = (
            select(ResearchJob, Company)
            .join(Company, Company.id == ResearchJob.company_id)
            .outerjoin(Valuation, Valuation.research_job_id == ResearchJob.id)
            .where(ResearchJob.status == ResearchJobStatus.COMPLETED, *([] if revalue else [Valuation.id.is_(None)]))
            .order_by(ResearchJob.created_at)
        )
        if tickers:
            query = query.where(Company.ticker.in_([t.upper() for t in tickers]))
        jobs = list(session.execute(query))
    facts_by_cik: dict[str, dict] = {}
    for job, company in jobs:
        if company.cik not in facts_by_cik:
            facts_by_cik[company.cik] = {p.period_end: p for p in extract_annual_periods(sec.company_facts(company.cik), years=10).periods}
        periods = facts_by_cik[company.cik]
        with SessionLocal() as session:
            for snapshot in session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.research_job_id == job.id)):
                extracted = periods.get(snapshot.period_end_date)
                if extracted is None:
                    continue
                for name in VALUATION_MONEY_FIELDS:
                    if getattr(snapshot, name) is None and name in extracted.values:
                        setattr(snapshot, name, extracted.values[name])
                        snapshot.provenance = {**(snapshot.provenance or {}), name: extracted.provenance[name]}
            session.flush()
            values, metrics = compute_valuation(session, job.id, risk_free)
            save_valuation(session, job.id, job.ticker, values, metrics)
            session.commit()
        outcome = f"${values['value_per_share']:,.2f} a share" if values["status"] == "valued" else f"skipped: {values['skip_reason']}"
        lines.append(f"{company.ticker:<6} {job.created_at:%Y-%m-%d} {str(job.id)[:8]}  {outcome}")
    return lines


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--revalue"]
    for line in backfill(args or None, revalue="--revalue" in sys.argv):
        print(line)
