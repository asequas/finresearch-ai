import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.research_job import ResearchJob

# Reported line items copied from SEC XBRL. Values are in `currency` units (not thousands).
CORE_MONEY_FIELDS = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "research_and_development",
    "interest_expense",
    "cash",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "debt",
)
# Extra facts the DCF needs (ADR 0010). Often legitimately absent (no leases, no minority interest), so reports
# don't list them as gaps; the valuation states its own assumptions when they're missing.
VALUATION_MONEY_FIELDS = (
    "depreciation_amortization",
    "income_tax_expense",
    "pretax_income",
    "short_term_investments",
    "lease_liabilities",
    "minority_interest",
    "share_based_compensation",
)
MONEY_FIELDS = CORE_MONEY_FIELDS + VALUATION_MONEY_FIELDS


def _money() -> Mapped[Decimal | None]:
    return mapped_column(Numeric(24, 4), nullable=True)


class FinancialSnapshot(Base):
    """Reported facts for one fiscal period, frozen for one research job (ADR 0005)."""

    __tablename__ = "financial_snapshots"
    __table_args__ = (
        Index(
            "ix_financial_snapshots_job_ticker",
            "research_job_id",
            "ticker",
        ),
        UniqueConstraint(
            "research_job_id",
            "ticker",
            "period",
            name="uq_financial_snapshots_job_ticker_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    research_job: Mapped["ResearchJob"] = relationship(
        back_populates="financial_snapshots",
    )

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    # e.g. "FY2024"
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)

    revenue: Mapped[Decimal | None] = _money()
    cost_of_revenue: Mapped[Decimal | None] = _money()
    gross_profit: Mapped[Decimal | None] = _money()
    operating_income: Mapped[Decimal | None] = _money()
    net_income: Mapped[Decimal | None] = _money()
    operating_cash_flow: Mapped[Decimal | None] = _money()
    capital_expenditure: Mapped[Decimal | None] = _money()
    research_and_development: Mapped[Decimal | None] = _money()
    interest_expense: Mapped[Decimal | None] = _money()
    cash: Mapped[Decimal | None] = _money()
    current_assets: Mapped[Decimal | None] = _money()
    current_liabilities: Mapped[Decimal | None] = _money()
    total_assets: Mapped[Decimal | None] = _money()
    total_liabilities: Mapped[Decimal | None] = _money()
    stockholders_equity: Mapped[Decimal | None] = _money()
    debt: Mapped[Decimal | None] = _money()
    depreciation_amortization: Mapped[Decimal | None] = _money()
    income_tax_expense: Mapped[Decimal | None] = _money()
    pretax_income: Mapped[Decimal | None] = _money()
    short_term_investments: Mapped[Decimal | None] = _money()
    lease_liabilities: Mapped[Decimal | None] = _money()
    minority_interest: Mapped[Decimal | None] = _money()
    share_based_compensation: Mapped[Decimal | None] = _money()

    eps: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    diluted_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)

    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    # field -> {concept, accession, form, filed, unit}
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
