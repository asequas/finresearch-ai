import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Valuation(Base):
    """The default DCF valuation for a research job (ADR 0010), with every input it used.

    `inputs` is the full DcfInputs record (values and sources), so the valuation can be recomputed exactly and
    what-if variations start from the same Rf, betas and ERP.
    """

    __tablename__ = "valuations"
    __table_args__ = (CheckConstraint("status IN ('valued', 'skipped')", name="ck_valuations_status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="fcff_three_stage")
    calculation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    value_per_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    equity_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    operating_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # derived, projection, terminal, bridge, sensitivity
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
