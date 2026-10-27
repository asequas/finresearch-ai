import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from backend.schemas.research import ResearchJobResponse


class CompanyOut(BaseModel):
    id: uuid.UUID
    cik: str
    ticker: str
    name: str
    sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None
    exchange: str | None


class FilingOut(BaseModel):
    id: uuid.UUID
    title: str
    form: str | None
    accession: str | None
    filed: date | None
    period: date | None
    url: str


class MetricOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    period: str
    fiscal_year: int | None
    value: Decimal
    unit: str
    formula: str
    inputs: dict
    calculation_version: str


class EvidenceOut(BaseModel):
    id: uuid.UUID
    quote: str
    quote_verified: bool
    section: str | None
    context: str | None
    document: FilingOut


class ClaimOut(BaseModel):
    id: uuid.UUID
    section: str
    claim_type: str
    text: str
    importance: int
    position: int
    verification_status: str
    verification_note: str | None
    evidence: list[EvidenceOut]
    metrics: list[MetricOut]


class FinancialValue(BaseModel):
    value: Decimal | None
    provenance: dict | None


class FinancialPeriodOut(BaseModel):
    period: str
    fiscal_year: int | None
    period_end_date: date
    currency: str
    source: str
    retrieved_at: datetime | None
    values: dict[str, FinancialValue]


class Assumption(BaseModel):
    driver: str
    assumption: str
    basis: str


class Scenario(BaseModel):
    name: str
    summary: str
    assumptions: list[Assumption]


class RiskOut(BaseModel):
    title: str
    description: str
    severity: str
    claim_ids: list[uuid.UUID]


class KeyPointOut(BaseModel):
    text: str
    claim_ids: list[uuid.UUID]


class VerificationSummary(BaseModel):
    total: int
    supported: int
    partially_supported: int
    unsupported: int
    not_verified: int


class ReportResponse(BaseModel):
    job: ResearchJobResponse
    company: CompanyOut
    headline: str
    direct_answer: str
    executive_summary: str
    key_points: list[KeyPointOut]
    investment_thesis: str | None
    scenarios: list[Scenario]
    risks: list[RiskOut]
    open_questions: list[str]
    limitations: list[str]
    disclaimer: str
    data_as_of: date | None
    generated_at: datetime
    models_used: dict | None
    filings: list[FilingOut]
    financials: list[FinancialPeriodOut]
    metrics: list[MetricOut]
    claims: list[ClaimOut]
    verification_summary: VerificationSummary


class CompanySummary(BaseModel):
    company: CompanyOut
    job_count: int
    latest_job_id: uuid.UUID
    latest_job_status: str
    latest_report_job_id: uuid.UUID | None
    latest_activity_at: datetime
