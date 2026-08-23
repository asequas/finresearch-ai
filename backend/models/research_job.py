import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.agent_run import AgentRun
    from backend.models.financial_snapshot import FinancialSnapshot
    from backend.models.report import Report
    from backend.models.claim import Claim


class ResearchJobStatus(str, PyEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchStage(str, PyEnum):
    PLANNING = "planning"
    FINANCIAL_RESEARCH = "financial_research"
    DOCUMENT_RESEARCH = "document_research"
    NEWS_RESEARCH = "news_research"
    RAG = "rag"
    VALUATION = "valuation"
    RISK_ANALYSIS = "risk_analysis"
    VERIFICATION = "verification"
    SYNTHESIS = "synthesis"


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    __table_args__ = (
        Index("ix_research_jobs_status", "status"),
        Index(
            "ix_research_jobs_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    company: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    ticker: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    status: Mapped[ResearchJobStatus] = mapped_column(
        Enum(
            ResearchJobStatus,
            name="research_job_status",
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ResearchJobStatus.QUEUED,
    )

    current_stage: Mapped[ResearchStage | None] = mapped_column(
        String(64),
        nullable=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    user: Mapped["User"] = relationship(
        back_populates="research_jobs",
    )

    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="research_job",
        cascade="all, delete-orphan",
    )

    financial_snapshots: Mapped[list["FinancialSnapshot"]] = relationship(
        back_populates="research_job",
        cascade="all, delete-orphan",
    )

    claims: Mapped[list["Claim"]] = relationship(
        back_populates="research_job",
        cascade="all, delete-orphan",
    )


    report: Mapped["Report | None"] = relationship(
        back_populates="research_job",
        uselist=False,
        cascade="all, delete-orphan",
    )