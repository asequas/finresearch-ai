"""Assembles the report reader payload: sections, claims with evidence and calculations."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    CalculatedMetric,
    Claim,
    ClaimEvidence,
    ClaimMetric,
    Company,
    Document,
    DocumentChunk,
    Evidence,
    FinancialSnapshot,
    Report,
    ResearchJob,
    ResearchJobDocument,
)
from backend.models.financial_snapshot import MONEY_FIELDS
from backend.models.research_job import ResearchJobStatus
from backend.schemas.report import (
    ClaimOut,
    CompanyDetail,
    CompanyOut,
    CompanySummary,
    EvidenceOut,
    FilingOut,
    FinancialPeriodOut,
    FinancialValue,
    MetricOut,
    ReportResponse,
    VerificationSummary,
)
from backend.schemas.research import ResearchJobResponse
from backend.services.errors import NotFoundError

SNAPSHOT_FIELDS = MONEY_FIELDS + ("eps", "diluted_shares")


def _company_out(company: Company) -> CompanyOut:
    return CompanyOut(
        id=company.id, cik=company.cik, ticker=company.ticker, name=company.name, sic=company.sic,
        sic_description=company.sic_description, fiscal_year_end=company.fiscal_year_end, exchange=company.exchange,
    )


def _filing_out(document: Document) -> FilingOut:
    return FilingOut(
        id=document.id, title=document.title, form=document.form_type, accession=document.accession_number,
        filed=document.filed_at, period=document.document_date, url=document.url,
    )


def _metric_out(metric: CalculatedMetric) -> MetricOut:
    return MetricOut(
        id=metric.id, key=metric.metric_key, label=metric.label, period=metric.period, fiscal_year=metric.fiscal_year,
        value=metric.value, unit=metric.unit, formula=metric.formula, inputs=metric.inputs,
        calculation_version=metric.calculation_version,
    )


def _financials_out(snapshots: list[FinancialSnapshot]) -> list[FinancialPeriodOut]:
    return [
        FinancialPeriodOut(
            period=s.period, fiscal_year=s.fiscal_year, period_end_date=s.period_end_date, currency=s.currency,
            source=s.source, retrieved_at=s.retrieved_at,
            values={
                name: FinancialValue(value=getattr(s, name), provenance=(s.provenance or {}).get(name))
                for name in SNAPSHOT_FIELDS
            },
        )
        for s in snapshots
    ]


class ReportService:
    def get_report(self, session: Session, *, job_id: UUID, user_id: UUID) -> ReportResponse:
        job = session.scalar(select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id))
        if job is None:
            raise NotFoundError("Research job not found")
        report = session.scalar(select(Report).where(Report.research_job_id == job_id))
        if report is None or job.company_id is None:
            raise NotFoundError("This job has no report yet")
        company = session.get(Company, job.company_id)

        documents = list(
            session.scalars(
                select(Document)
                .join(ResearchJobDocument, ResearchJobDocument.document_id == Document.id)
                .where(ResearchJobDocument.research_job_id == job_id)
                .order_by(Document.filed_at.desc())
            )
        )
        filings = {d.id: _filing_out(d) for d in documents}

        metrics = list(
            session.scalars(
                select(CalculatedMetric)
                .where(CalculatedMetric.research_job_id == job_id)
                .order_by(CalculatedMetric.metric_key, CalculatedMetric.period)
            )
        )
        metric_out = {m.id: _metric_out(m) for m in metrics}

        claims = list(session.scalars(select(Claim).where(Claim.research_job_id == job_id).order_by(Claim.position)))
        claim_ids = [c.id for c in claims]

        evidence_by_claim: dict[UUID, list[EvidenceOut]] = {}
        rows = session.execute(
            select(ClaimEvidence.claim_id, Evidence, DocumentChunk.section, DocumentChunk.content, Document)
            .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
            .join(Document, Document.id == Evidence.document_id)
            .join(DocumentChunk, DocumentChunk.id == Evidence.document_chunk_id, isouter=True)
            .where(ClaimEvidence.claim_id.in_(claim_ids))
        )
        for claim_id, evidence, section, context, document in rows:
            evidence_by_claim.setdefault(claim_id, []).append(
                EvidenceOut(
                    id=evidence.id, quote=evidence.excerpt, quote_verified=evidence.quote_verified, section=section,
                    context=context, document=filings.get(document.id) or _filing_out(document),
                )
            )

        metrics_by_claim: dict[UUID, list[MetricOut]] = {}
        for claim_id, metric_id in session.execute(
            select(ClaimMetric.claim_id, ClaimMetric.metric_id).where(ClaimMetric.claim_id.in_(claim_ids))
        ):
            if metric_id in metric_out:
                metrics_by_claim.setdefault(claim_id, []).append(metric_out[metric_id])

        claim_out = [
            ClaimOut(
                id=c.id, section=c.section, claim_type=c.claim_type, text=c.claim_text, importance=c.importance,
                position=c.position, verification_status=c.verification_status, verification_note=c.verification_note,
                evidence=evidence_by_claim.get(c.id, []), metrics=metrics_by_claim.get(c.id, []),
            )
            for c in claims
        ]
        counts = {status: sum(1 for c in claims if c.verification_status == status)
                  for status in ("supported", "partially_supported", "unsupported", "not_verified")}

        snapshots = list(
            session.scalars(
                select(FinancialSnapshot)
                .where(FinancialSnapshot.research_job_id == job_id)
                .order_by(FinancialSnapshot.period_end_date)
            )
        )
        financials = _financials_out(snapshots)

        full = report.full_report or {}
        job_out = ResearchJobResponse.model_validate(job)
        job_out.has_report = True
        return ReportResponse(
            job=job_out,
            company=_company_out(company),
            headline=full.get("headline", ""),
            direct_answer=full.get("direct_answer", ""),
            executive_summary=report.executive_summary,
            key_points=full.get("key_points", []),
            investment_thesis=report.investment_thesis,
            scenarios=(report.valuation_summary or {}).get("scenarios", []),
            risks=(report.risk_summary or {}).get("risks", []),
            open_questions=full.get("open_questions", []),
            limitations=report.limitations or [],
            disclaimer=full.get("disclaimer", ""),
            data_as_of=report.data_as_of,
            generated_at=report.updated_at,
            models_used=report.models_used,
            filings=list(filings.values()),
            financials=financials,
            metrics=list(metric_out.values()),
            claims=claim_out,
            verification_summary=VerificationSummary(total=len(claims), **counts),
            research=(report.full_report or {}).get("research"),
        )

    def list_companies(self, session: Session, *, user_id: UUID) -> list[CompanySummary]:
        jobs = list(
            session.scalars(
                select(ResearchJob)
                .where(ResearchJob.user_id == user_id, ResearchJob.company_id.is_not(None))
                .order_by(ResearchJob.created_at.desc())
            )
        )
        with_reports = set(
            session.scalars(select(Report.research_job_id).where(Report.research_job_id.in_([j.id for j in jobs])))
        ) if jobs else set()
        companies = {c.id: c for c in session.scalars(select(Company).where(Company.id.in_({j.company_id for j in jobs})))} if jobs else {}

        summaries: dict[UUID, CompanySummary] = {}
        for job in jobs:  # newest first
            summary = summaries.get(job.company_id)
            if summary is None:
                summaries[job.company_id] = CompanySummary(
                    company=_company_out(companies[job.company_id]), display_name=job.company,
                    job_count=1, latest_job_id=job.id,
                    latest_job_status=job.status.value,
                    latest_report_job_id=job.id if job.id in with_reports else None,
                    latest_activity_at=job.updated_at,
                )
            else:
                summary.job_count += 1
                if summary.latest_report_job_id is None and job.id in with_reports:
                    summary.latest_report_job_id = job.id
        return list(summaries.values())

    def get_company(self, session: Session, *, ticker: str, user_id: UUID) -> CompanyDetail:
        """A company workspace: the latest report's figures plus every job this user ran on it."""
        jobs = list(
            session.scalars(
                select(ResearchJob)
                .join(Company, Company.id == ResearchJob.company_id)
                .where(ResearchJob.user_id == user_id, Company.ticker == ticker.upper())
                .order_by(ResearchJob.created_at.desc())
            )
        )
        if not jobs:
            raise NotFoundError(f"No research on {ticker.upper()} yet")
        company = session.get(Company, jobs[0].company_id)
        report_job_ids = set(
            session.scalars(select(Report.research_job_id).where(Report.research_job_id.in_([j.id for j in jobs])))
        )
        latest = next((j for j in jobs if j.id in report_job_ids), None)
        snapshots: list[FinancialSnapshot] = []
        metrics: list[CalculatedMetric] = []
        data_as_of = None
        if latest is not None:
            snapshots = list(
                session.scalars(
                    select(FinancialSnapshot)
                    .where(FinancialSnapshot.research_job_id == latest.id)
                    .order_by(FinancialSnapshot.period_end_date)
                )
            )
            metrics = list(
                session.scalars(
                    select(CalculatedMetric)
                    .where(CalculatedMetric.research_job_id == latest.id)
                    .order_by(CalculatedMetric.metric_key, CalculatedMetric.period)
                )
            )
            data_as_of = snapshots[-1].period_end_date if snapshots else None
        job_out = []
        for job in jobs:
            item = ResearchJobResponse.model_validate(job)
            item.has_report = job.id in report_job_ids
            job_out.append(item)
        return CompanyDetail(
            company=_company_out(company),
            latest_report_job_id=latest.id if latest else None,
            data_as_of=data_as_of,
            financials=_financials_out(snapshots),
            metrics=[_metric_out(m) for m in metrics],
            jobs=job_out,
        )
