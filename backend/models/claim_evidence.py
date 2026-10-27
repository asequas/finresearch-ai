import uuid

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        # The PK leads with claim_id; "which claims cite this evidence" needs its own index.
        Index("ix_claim_evidence_evidence_id", "evidence_id"),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        primary_key=True,
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        primary_key=True,
    )

    relevance_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )