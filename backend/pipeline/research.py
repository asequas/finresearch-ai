"""The research pipeline (ADR 0006). Each stage reads its inputs from the database
and writes its outputs idempotently (delete-then-insert per job, or upsert), so a
retried or resumed stage never duplicates data.
"""
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.analysis.chunking import chunk_text
from backend.analysis.metrics import FinancialPeriod, compute_metrics, format_metric
from backend.analysis.retrieval import RetrievedChunk, hybrid_search
from backend.analysis.verification import quote_in_source, unmatched_numbers
from backend.core.config import settings
from backend.llm.client import LLMClient, get_llm_client
from backend.models.calculated_metric import CalculatedMetric
from backend.models.claim import Claim
from backend.models.claim_evidence import ClaimEvidence
from backend.models.claim_metric import ClaimMetric
from backend.models.company import Company
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.evidence import Evidence
from backend.models.financial_snapshot import MONEY_FIELDS, FinancialSnapshot
from backend.models.report import Report
from backend.models.research_job import ResearchJob, ResearchStage
from backend.models.research_job_document import ResearchJobDocument
from backend.pipeline import prompts
from backend.pipeline.base import JobContext, PermanentError
from backend.sources.filing_text import html_to_text, split_sections
from backend.sources.sec import SecClient, is_financial_sector
from backend.sources.xbrl import UnsupportedFinancialsError, extract_annual_periods

logger = logging.getLogger(__name__)

SNAPSHOT_FIELDS = MONEY_FIELDS + ("eps", "diluted_shares")
MAX_EXCERPTS = 28
DISCLAIMER = (
    "Generated from SEC filings for research and education. Not investment advice. "
    "Verify material facts against the linked filings before acting."
)


@dataclass
class Services:
    sec_factory: Callable[[], SecClient]
    llm_factory: Callable[[], LLMClient]
    _sec: SecClient | None = field(default=None, init=False)
    _llm: LLMClient | None = field(default=None, init=False)

    @property
    def sec(self) -> SecClient:
        if self._sec is None:
            self._sec = self.sec_factory()
        return self._sec

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = self.llm_factory()
        return self._llm


def _record(ctx: JobContext, result) -> None:
    ctx.usage.add_llm_call(model=result.model, input_tokens=result.input_tokens, output_tokens=result.output_tokens)


def _read(ctx: JobContext):
    return ctx.session_factory()


def _company(session: Session, job_id: UUID) -> Company:
    company = session.scalar(
        select(Company).join(ResearchJob, ResearchJob.company_id == Company.id).where(ResearchJob.id == job_id)
    )
    if company is None:
        raise PermanentError("Company was not resolved for this job.")
    return company


def _job_documents(session: Session, job_id: UUID) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .join(ResearchJobDocument, ResearchJobDocument.document_id == Document.id)
            .where(ResearchJobDocument.research_job_id == job_id)
            .order_by(Document.filed_at.desc())
        )
    )


def _metrics(session: Session, job_id: UUID) -> list[CalculatedMetric]:
    return list(
        session.scalars(
            select(CalculatedMetric)
            .where(CalculatedMetric.research_job_id == job_id)
            .order_by(CalculatedMetric.metric_key, CalculatedMetric.period)
        )
    )


def _latest_period_end(session: Session, job_id: UUID) -> date | None:
    return session.scalar(
        select(FinancialSnapshot.period_end_date)
        .where(FinancialSnapshot.research_job_id == job_id)
        .order_by(FinancialSnapshot.period_end_date.desc())
        .limit(1)
    )


def _metric_lines(metrics: list[CalculatedMetric]) -> tuple[str, dict[str, CalculatedMetric]]:
    """Render metrics as 'M1: Operating margin FY2024 = 44.6% (operating_income / revenue)'."""
    ids: dict[str, CalculatedMetric] = {}
    lines = []
    for i, metric in enumerate(metrics, start=1):
        ids[f"M{i}"] = metric
        lines.append(
            f"M{i}: {metric.label} {metric.period} = {format_metric(metric.value, metric.unit)} ({metric.formula})"
        )
    return "\n".join(lines) or "(no metrics available)", ids


# ---- 1. Resolve company ----------------------------------------------------

@dataclass
class ResolveCompany:
    services: Services
    name: ResearchStage = ResearchStage.RESOLVING_COMPANY
    weight: int = 5

    def run(self, ctx: JobContext) -> None:
        record = self.services.sec.resolve_ticker(ctx.ticker)
        if is_financial_sector(record.sic):
            raise PermanentError(
                f"{record.name} is in a financial-sector industry ({record.sic_description}). Banks, insurers "
                "and REITs need different metrics and are not supported in this version."
            )
        values = dict(
            cik=record.cik, ticker=record.ticker, name=record.name, sic=record.sic,
            sic_description=record.sic_description, fiscal_year_end=record.fiscal_year_end,
            exchange=record.exchange, retrieved_at=datetime.now(timezone.utc),
        )
        with ctx.transaction() as session:
            company_id = session.execute(
                insert(Company)
                .values(**values)
                .on_conflict_do_update(index_elements=["cik"], set_={k: v for k, v in values.items() if k != "cik"})
                .returning(Company.id)
            ).scalar_one()
            session.execute(update(ResearchJob).where(ResearchJob.id == ctx.job_id).values(company_id=company_id))
        ctx.usage.metadata = {"cik": record.cik, "name": record.name, "sic": record.sic}


# ---- 2. Fetch filings ------------------------------------------------------

@dataclass
class FetchFilings:
    services: Services
    name: ResearchStage = ResearchStage.FETCHING_FILINGS
    weight: int = 10

    def run(self, ctx: JobContext) -> None:
        with _read(ctx) as session:
            company = _company(session, ctx.job_id)
            cik, company_id, company_name = company.cik, company.id, company.name

        annual = self.services.sec.latest_filings(cik, "10-K", limit=1)
        if not annual:
            raise PermanentError(
                f"{company_name} has no 10-K on SEC EDGAR (foreign issuers file 20-F, which is not supported yet)."
            )
        selected = [("primary", annual[0])]
        quarterly = self.services.sec.latest_filings(cik, "10-Q", limit=1)
        if quarterly and quarterly[0].filed > annual[0].filed:
            selected.append(("supplementary", quarterly[0]))

        rows = []
        for role, filing in selected:
            ctx.checkpoint()
            raw = self.services.sec.filing_document(filing)
            rows.append((role, filing, hashlib.sha256(raw).hexdigest()))

        with ctx.transaction() as session:
            session.execute(delete(ResearchJobDocument).where(ResearchJobDocument.research_job_id == ctx.job_id))
            for role, filing, content_hash in rows:
                session.execute(
                    insert(Document)
                    .values(
                        company_id=company_id,
                        source_type="sec_filing",
                        form_type=filing.form,
                        accession_number=filing.accession_number,
                        title=f"{company_name} {filing.form} for period ending {filing.report_date or filing.filed}",
                        url=filing.url,
                        publisher="U.S. Securities and Exchange Commission",
                        document_date=filing.report_date,
                        filed_at=filing.filed,
                        content_hash=content_hash,
                        retrieved_at=datetime.now(timezone.utc),
                        extra_metadata={"primary_document": filing.primary_document, "cik": cik},
                    )
                    .on_conflict_do_nothing(index_elements=["accession_number"])
                )
                document_id = session.scalar(
                    select(Document.id).where(Document.accession_number == filing.accession_number)
                )
                session.add(ResearchJobDocument(research_job_id=ctx.job_id, document_id=document_id, role=role))
        ctx.usage.metadata = {"filings": [f.accession_number for _, f, _ in rows]}


# ---- 3. Extract financials -------------------------------------------------

@dataclass
class ExtractFinancials:
    services: Services
    name: ResearchStage = ResearchStage.EXTRACTING_FINANCIALS
    weight: int = 10

    def run(self, ctx: JobContext) -> None:
        with _read(ctx) as session:
            cik = _company(session, ctx.job_id).cik
        try:
            extraction = extract_annual_periods(self.services.sec.company_facts(cik), years=5)
        except UnsupportedFinancialsError as exc:
            raise PermanentError(str(exc)) from exc

        retrieved_at = datetime.now(timezone.utc)
        with ctx.transaction() as session:
            session.execute(delete(FinancialSnapshot).where(FinancialSnapshot.research_job_id == ctx.job_id))
            for period in extraction.periods:
                revenue_source = period.provenance.get("revenue") or next(iter(period.provenance.values()), {})
                session.add(
                    FinancialSnapshot(
                        research_job_id=ctx.job_id,
                        ticker=ctx.ticker,
                        period=f"FY{period.fiscal_year}",
                        fiscal_year=period.fiscal_year,
                        period_end_date=period.period_end,
                        currency=extraction.currency,
                        source="SEC EDGAR XBRL companyfacts",
                        source_reference=revenue_source.get("accession"),
                        provenance=period.provenance,
                        retrieved_at=retrieved_at,
                        **{name: period.values.get(name) for name in SNAPSHOT_FIELDS},
                    )
                )
        ctx.usage.metadata = {"years": [p.fiscal_year for p in extraction.periods], "missing": extraction.missing}


# ---- 4. Compute metrics ----------------------------------------------------

@dataclass
class ComputeMetrics:
    name: ResearchStage = ResearchStage.COMPUTING_METRICS
    weight: int = 5

    def run(self, ctx: JobContext) -> None:
        with _read(ctx) as session:
            snapshots = list(
                session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.research_job_id == ctx.job_id))
            )
        report = compute_metrics(
            [
                FinancialPeriod(fiscal_year=s.fiscal_year, **{name: getattr(s, name) for name in SNAPSHOT_FIELDS if name != "diluted_shares"})
                for s in snapshots
            ]
        )
        with ctx.transaction() as session:
            session.execute(delete(CalculatedMetric).where(CalculatedMetric.research_job_id == ctx.job_id))
            for result in report.results:
                session.add(
                    CalculatedMetric(
                        research_job_id=ctx.job_id, ticker=ctx.ticker, metric_key=result.key, label=result.label,
                        period=result.period, fiscal_year=result.fiscal_year, value=result.value, unit=result.unit,
                        formula=result.formula, inputs=result.inputs, calculation_version=result.calculation_version,
                    )
                )
        ctx.usage.metadata = {
            "computed": len(report.results),
            "skipped": [{"metric": s.key, "period": s.period, "reason": s.reason} for s in report.skipped],
        }


# ---- 5. Index documents ----------------------------------------------------

@dataclass
class IndexDocuments:
    services: Services
    name: ResearchStage = ResearchStage.INDEXING_DOCUMENTS
    weight: int = 20

    def run(self, ctx: JobContext) -> None:
        with _read(ctx) as session:
            documents = [(d.id, d.form_type, d.url, d.indexed_at) for d in _job_documents(session, ctx.job_id)]

        indexed = 0
        for document_id, form, url, indexed_at in documents:
            if indexed_at is not None:
                continue  # shared across jobs: another job already indexed this filing
            ctx.checkpoint()
            raw = self.services.sec.fetch(url, max_age_seconds=None)
            if raw is None:
                raise PermanentError(f"Filing document {url} is missing on SEC EDGAR.")
            text = html_to_text(raw.decode("utf-8", errors="replace"))
            sections = split_sections(text, form=form)
            if not sections:
                logger.warning("no standard sections found in %s; indexing the whole document", url)
                sections = []
                chunks = chunk_text("document", text[:300_000])
            else:
                chunks = []
                for section in sections:
                    chunks.extend(chunk_text(section.key, section.text, start_index=len(chunks)))

            embeddings: list[list[float]] = []
            for start in range(0, len(chunks), 100):
                ctx.checkpoint()
                embeddings.extend(self.services.llm.embed([c.content for c in chunks[start : start + 100]], task="document"))

            with ctx.transaction() as session:
                locked = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
                if locked.indexed_at is not None:
                    continue  # lost a benign race with another job
                session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
                for chunk, embedding in zip(chunks, embeddings):
                    session.add(
                        DocumentChunk(
                            document_id=document_id, chunk_index=chunk.index, section=chunk.section,
                            content=chunk.content, embedding=embedding,
                        )
                    )
                locked.indexed_at = datetime.now(timezone.utc)
                locked.extra_metadata = {**(locked.extra_metadata or {}), "sections": [s.key for s in sections]}
            indexed += len(chunks)
        ctx.usage.metadata = {"chunks_indexed": indexed}


# ---- 6. Analyze ------------------------------------------------------------

@dataclass
class Analyze:
    services: Services
    name: ResearchStage = ResearchStage.ANALYZING
    weight: int = 25

    def run(self, ctx: JobContext) -> None:
        llm = self.services.llm
        with _read(ctx) as session:
            documents = _job_documents(session, ctx.job_id)
            document_ids = [d.id for d in documents]
            metrics = _metrics(session, ctx.job_id)
            period_end = _latest_period_end(session, ctx.job_id)
        metric_text, metric_ids = _metric_lines(metrics)

        plan = llm.generate_json(
            prompt=prompts.PLAN_PROMPT.format(query=ctx.query, company=ctx.company, ticker=ctx.ticker, period_end=period_end),
            schema=prompts.ResearchPlan,
            system=prompts.ANALYST_SYSTEM,
        )
        _record(ctx, plan)
        questions = [ctx.query, *plan.value.sub_questions[:6]]

        chunks: dict[UUID, RetrievedChunk] = {}
        query_embeddings = llm.embed(questions, task="query")
        with _read(ctx) as session:
            for question, embedding in zip(questions, query_embeddings):
                for hit in hybrid_search(session, query_text=question, query_embedding=embedding, document_ids=document_ids, limit=6):
                    chunks.setdefault(hit.id, hit)
        ctx.checkpoint()
        excerpts = list(chunks.values())[:MAX_EXCERPTS]
        excerpt_ids = {f"E{i}": chunk for i, chunk in enumerate(excerpts, start=1)}
        excerpt_text = "\n\n".join(f"[{eid}] ({chunk.section})\n{chunk.content}" for eid, chunk in excerpt_ids.items())

        draft = llm.generate_json(
            prompt=prompts.DRAFT_PROMPT.format(
                query=ctx.query, company=ctx.company, ticker=ctx.ticker, metrics=metric_text,
                excerpts=excerpt_text or "(no excerpts retrieved)", sections=", ".join(prompts.SECTIONS),
            ),
            schema=prompts.ClaimDraft,
            system=prompts.ANALYST_SYSTEM,
            strong=True,
        )
        _record(ctx, draft)

        with ctx.transaction() as session:
            _delete_claims(session, ctx.job_id)
            for position, item in enumerate(draft.value.claims):
                referenced = [metric_ids[ref] for ref in item.metric_refs if ref in metric_ids]
                claim = Claim(
                    research_job_id=ctx.job_id, claim_text=item.text.strip(), claim_type=item.claim_type,
                    section=item.section, position=position, importance=item.importance,
                    verification_status="not_verified",
                )
                session.add(claim)
                session.flush()
                for metric in {m.id: m for m in referenced}.values():
                    session.add(ClaimMetric(claim_id=claim.id, metric_id=metric.id))
                for ref in item.evidence:
                    chunk = excerpt_ids.get(ref.excerpt_id)
                    if chunk is None or not ref.quote.strip():
                        continue
                    evidence = Evidence(
                        document_id=chunk.document_id, document_chunk_id=chunk.id, excerpt=ref.quote.strip(),
                        source_url=next((d.url for d in documents if d.id == chunk.document_id), None),
                    )
                    session.add(evidence)
                    session.flush()
                    session.add(ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relevance_score=None))
        ctx.usage.metadata = {"questions": questions, "excerpts": len(excerpts), "claims": len(draft.value.claims)}


def _delete_claims(session: Session, job_id: UUID) -> None:
    claim_ids = select(Claim.id).where(Claim.research_job_id == job_id)
    evidence_ids = select(ClaimEvidence.evidence_id).where(ClaimEvidence.claim_id.in_(claim_ids))
    session.execute(delete(Evidence).where(Evidence.id.in_(evidence_ids)))
    session.execute(delete(Claim).where(Claim.research_job_id == job_id))


# ---- 7. Verify -------------------------------------------------------------

@dataclass
class Verify:
    services: Services
    name: ResearchStage = ResearchStage.VERIFYING
    weight: int = 15

    def run(self, ctx: JobContext) -> None:
        with _read(ctx) as session:
            claims = list(session.scalars(select(Claim).where(Claim.research_job_id == ctx.job_id).order_by(Claim.position)))
            metrics_by_id = {m.id: m for m in _metrics(session, ctx.job_id)}
            claim_metric_ids: dict[UUID, list[UUID]] = {}
            for claim_id, metric_id in session.execute(
                select(ClaimMetric.claim_id, ClaimMetric.metric_id)
                .join(Claim, Claim.id == ClaimMetric.claim_id)
                .where(Claim.research_job_id == ctx.job_id)
            ):
                claim_metric_ids.setdefault(claim_id, []).append(metric_id)
            evidence_rows = session.execute(
                select(ClaimEvidence.claim_id, Evidence, DocumentChunk.content)
                .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
                .join(DocumentChunk, DocumentChunk.id == Evidence.document_chunk_id, isouter=True)
                .join(Claim, Claim.id == ClaimEvidence.claim_id)
                .where(Claim.research_job_id == ctx.job_id)
            ).all()

        quote_ok: dict[UUID, bool] = {}
        quotes_by_claim: dict[UUID, list[str]] = {}
        for claim_id, evidence, chunk_content in evidence_rows:
            ok = bool(chunk_content) and quote_in_source(evidence.excerpt, chunk_content)
            quote_ok[evidence.id] = ok
            if ok:
                quotes_by_claim.setdefault(claim_id, []).append(evidence.excerpt)

        decided: dict[UUID, tuple[str, str]] = {}
        to_judge: list[Claim] = []
        for claim in claims:
            referenced = [metrics_by_id[m] for m in claim_metric_ids.get(claim.id, []) if m in metrics_by_id]
            if claim.claim_type == "calculation":
                if not referenced:
                    decided[claim.id] = ("unsupported", "No computed metric backs this calculation.")
                    continue
                stray = unmatched_numbers(claim.claim_text, [(m.value, m.unit) for m in referenced])
                if stray:
                    decided[claim.id] = ("unsupported", f"Numbers {', '.join(stray)} don't match the cited metric.")
                else:
                    shown = ", ".join(f"{m.label} {m.period} = {format_metric(m.value, m.unit)}" for m in referenced)
                    decided[claim.id] = ("supported", f"Matches computed metric: {shown}.")
            elif claim.claim_type == "fact" and not quotes_by_claim.get(claim.id):
                decided[claim.id] = ("unsupported", "No cited quote was found verbatim in the filing.")
            elif not quotes_by_claim.get(claim.id) and not referenced:
                decided[claim.id] = ("unsupported", "No verifiable evidence was cited.")
            else:
                to_judge.append(claim)

        if to_judge:
            blocks = []
            for i, claim in enumerate(to_judge, start=1):
                material = [f'  quote: "{q}"' for q in quotes_by_claim.get(claim.id, [])]
                for metric_id in claim_metric_ids.get(claim.id, []):
                    m = metrics_by_id[metric_id]
                    material.append(f"  metric: {m.label} {m.period} = {format_metric(m.value, m.unit)}")
                blocks.append(f"C{i} [{claim.claim_type}] {claim.claim_text}\n" + "\n".join(material))
            judged = self.services.llm.generate_json(
                prompt=prompts.JUDGE_PROMPT.format(claims="\n\n".join(blocks)),
                schema=prompts.Judgements,
                system="You are a strict fact-checker for financial research.",
                temperature=0.0,
            )
            _record(ctx, judged)
            verdicts = {j.claim_id: j for j in judged.value.judgements}
            for i, claim in enumerate(to_judge, start=1):
                verdict = verdicts.get(f"C{i}")
                decided[claim.id] = (
                    (verdict.verdict, verdict.note) if verdict else ("not_verified", "The fact-checker returned no verdict.")
                )

        with ctx.transaction() as session:
            for evidence_id, ok in quote_ok.items():
                session.execute(update(Evidence).where(Evidence.id == evidence_id).values(quote_verified=ok))
            for claim_id, (status, note) in decided.items():
                session.execute(
                    update(Claim).where(Claim.id == claim_id).values(verification_status=status, verification_note=note)
                )
        counts: dict[str, int] = {}
        for status, _ in decided.values():
            counts[status] = counts.get(status, 0) + 1
        ctx.usage.metadata = {"verdicts": counts, "quotes_checked": len(quote_ok)}


# ---- 8. Synthesize ---------------------------------------------------------

def build_limitations(session: Session, job_id: UUID) -> list[str]:
    limitations = [
        "Market price data is out of scope, so there are no valuation multiples, price targets or returns.",
        "Debt uses reported long-term debt; leases and commercial paper may be excluded.",
    ]
    snapshots = list(session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.research_job_id == job_id)))
    for name in SNAPSHOT_FIELDS:
        years = [s.period for s in snapshots if getattr(s, name) is None]
        if years and len(years) == len(snapshots):
            limitations.append(f"{name.replace('_', ' ').capitalize()} is not reported in XBRL for any year analysed.")
        elif years:
            limitations.append(f"{name.replace('_', ' ').capitalize()} is missing for {', '.join(sorted(years))}.")
    unsupported = session.scalar(
        select(Claim.id).where(Claim.research_job_id == job_id, Claim.verification_status == "unsupported").limit(1)
    )
    if unsupported:
        limitations.append("Some drafted claims could not be verified; they appear in the evidence ledger, flagged.")
    return limitations


@dataclass
class Synthesize:
    services: Services
    name: ResearchStage = ResearchStage.SYNTHESIZING
    weight: int = 10

    def run(self, ctx: JobContext) -> None:
        with _read(ctx) as session:
            claims = list(
                session.scalars(
                    select(Claim)
                    .where(Claim.research_job_id == ctx.job_id, Claim.verification_status.in_(["supported", "partially_supported"]))
                    .order_by(Claim.position)
                )
            )
            metrics = _metrics(session, ctx.job_id)
            period_end = _latest_period_end(session, ctx.job_id)
            limitations = build_limitations(session, ctx.job_id)
            documents = _job_documents(session, ctx.job_id)
        if not claims:
            raise PermanentError("No claims survived verification, so no trustworthy report could be written.")

        claim_ids = {f"C{i}": claim for i, claim in enumerate(claims, start=1)}
        claim_text = "\n".join(
            f"{cid} [{c.section}/{c.claim_type}/{c.verification_status}] {c.claim_text}" for cid, c in claim_ids.items()
        )
        latest = [m for m in metrics if m.fiscal_year == (period_end.year if period_end else None) or "-" in m.period]
        metric_text, _ = _metric_lines(latest or metrics)

        result = self.services.llm.generate_json(
            prompt=prompts.SYNTHESIS_PROMPT.format(
                query=ctx.query, company=ctx.company, ticker=ctx.ticker, period_end=period_end,
                claims=claim_text, metrics=metric_text, limitations="\n".join(f"- {l}" for l in limitations),
            ),
            schema=prompts.ReportDraft,
            system=prompts.ANALYST_SYSTEM,
            strong=True,
            temperature=0.3,
        )
        _record(ctx, result)
        draft = result.value

        def resolve(ids: list[str]) -> list[str]:
            return [str(claim_ids[i].id) for i in ids if i in claim_ids]

        full_report = {
            "headline": draft.headline,
            "direct_answer": draft.direct_answer,
            "key_points": [{"text": p.text, "claim_ids": resolve(p.claim_ids)} for p in draft.key_points],
            "open_questions": draft.open_questions,
            "filings": [
                {"id": str(d.id), "form": d.form_type, "accession": d.accession_number, "filed": d.filed_at.isoformat() if d.filed_at else None,
                 "period": d.document_date.isoformat() if d.document_date else None, "url": d.url}
                for d in documents
            ],
            "disclaimer": DISCLAIMER,
        }
        values = dict(
            executive_summary=draft.executive_summary,
            investment_thesis=draft.investment_thesis,
            valuation_summary={"scenarios": [s.model_dump() for s in draft.scenarios]},
            risk_summary={"risks": [{**r.model_dump(exclude={"claim_ids"}), "claim_ids": resolve(r.claim_ids)} for r in draft.risks]},
            full_report=full_report,
            data_as_of=period_end,
            limitations=limitations,
            models_used={"fast": self.services.llm.fast_model, "strong": self.services.llm.strong_model,
                         "embedding": settings.gemini_embedding_model},
            updated_at=datetime.now(timezone.utc),
        )
        with ctx.transaction() as session:
            session.execute(
                insert(Report)
                .values(research_job_id=ctx.job_id, created_at=datetime.now(timezone.utc), **values)
                .on_conflict_do_update(index_elements=["research_job_id"], set_=values)
            )


def research_stages(services: Services | None = None) -> list:
    services = services or Services(
        sec_factory=lambda: SecClient(settings.sec_user_agent, settings.data_cache_dir),
        llm_factory=get_llm_client,
    )
    return [
        ResolveCompany(services),
        FetchFilings(services),
        ExtractFinancials(services),
        ComputeMetrics(),
        IndexDocuments(services),
        Analyze(services),
        Verify(services),
        Synthesize(services),
    ]
