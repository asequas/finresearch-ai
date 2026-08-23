import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Numeric, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.research_job import ResearchJob

class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"
    __table_args__ = (
        Index(
            "ix_financial_snapshots_job_ticker",
            "research_job_id",
            "ticker",
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

    ticker: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    period: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    period_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    revenue: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    net_income: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    operating_income: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    free_cash_flow: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    eps: Mapped[float | None] = mapped_column(
        Numeric(20, 6),
        nullable=True,
    )

    gross_margin: Mapped[float | None] = mapped_column(
        Numeric(10, 6),
        nullable=True,
    )

    operating_margin: Mapped[float | None] = mapped_column(
        Numeric(10, 6),
        nullable=True,
    )

    cash: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    debt: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    source_reference: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )