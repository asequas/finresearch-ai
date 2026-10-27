import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class CalculatedMetric(Base):
    """A deterministic calculation with its formula and named inputs (ADR 0005)."""

    __tablename__ = "calculated_metrics"
    __table_args__ = (
        UniqueConstraint(
            "research_job_id",
            "ticker",
            "metric_key",
            "period",
            name="uq_calculated_metrics_job_ticker_metric_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    # "FY2024" for point-in-time metrics, "FY2020-FY2024" for multi-year ones
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    # "ratio" (0.25 = 25%), "USD", "times"
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
