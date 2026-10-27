import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.agent_run import AgentRun
    from backend.models.research_job import ResearchJob
    from backend.models.evidence import Evidence


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index(
            "ix_claims_research_job_id",
            "research_job_id",
        ),
        CheckConstraint(
            "claim_type IN ('fact', 'calculation', 'interpretation')",
            name="ck_claims_claim_type",
        ),
        CheckConstraint(
            "verification_status IN ('supported', 'partially_supported', 'unsupported', 'not_verified')",
            name="ck_claims_verification_status",
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

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    metric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calculated_metrics.id", ondelete="SET NULL"),
        nullable=True,
    )

    section: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="analysis",
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    claim_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    claim_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    verification_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    research_job: Mapped["ResearchJob"] = relationship(
        back_populates="claims",
    )

    agent_run: Mapped["AgentRun | None"] = relationship(
        back_populates="claims",
    )

    evidence: Mapped[list["Evidence"]] = relationship(
        secondary="claim_evidence",
        back_populates="claims",
    )