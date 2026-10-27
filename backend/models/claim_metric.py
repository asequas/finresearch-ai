import uuid

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ClaimMetric(Base):
    """Which calculated metrics a claim relies on (a growth claim can cite several)."""

    __tablename__ = "claim_metrics"
    __table_args__ = (Index("ix_claim_metrics_metric_id", "metric_id"),)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calculated_metrics.id", ondelete="CASCADE"), primary_key=True
    )
