import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.agent_run import AgentRun
    from backend.models.financial_snapshot import FinancialSnapshot
    from backend.models.report import Report
    from backend.models.claim import Claim
    from backend.models.user import User


class ResearchJobStatus(str, PyEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchStage(str, PyEnum):
    RESOLVING_COMPANY = "resolving_company"
    FETCHING_FILINGS = "fetching_filings"
    EXTRACTING_FINANCIALS = "extracting_financials"
    COMPUTING_METRICS = "computing_metrics"
    VALUING = "valuing"  # deterministic DCF (ADR 0010)
    INDEXING_DOCUMENTS = "indexing_documents"
    ANALYZING = "analyzing"  # the linear pipeline's single analysis stage; kept valid for jobs that ran it
    # The research agent's graph nodes (ADR 0008).
    PLANNING = "planning"
    RESEARCHING = "researching"
    DRAFTING = "drafting"
    VERIFYING = "verifying"
    SYNTHESIZING = "synthesizing"


TERMINAL_STATUSES = frozenset(
    {ResearchJobStatus.COMPLETED, ResearchJobStatus.FAILED, ResearchJobStatus.CANCELLED}
)


def _sql_in(enum_cls: type[PyEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_cls)


def _values(enum_cls: type[PyEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_in(ResearchJobStatus)})",
            name="ck_research_jobs_status",
        ),
        CheckConstraint(
            f"current_stage IS NULL OR current_stage IN ({_sql_in(ResearchStage)})",
            name="ck_research_jobs_current_stage",
        ),
        CheckConstraint(
            "progress BETWEEN 0 AND 100",
            name="ck_research_jobs_progress",
        ),
        CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1",
            name="ck_research_jobs_attempts",
        ),
        Index(
            "ix_research_jobs_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_research_jobs_claimable",
            "run_after",
            "created_at",
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "ix_research_jobs_lease",
            "lease_expires_at",
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "uq_research_jobs_user_idempotency_key",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
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

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
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
            length=32,
            values_callable=_values,
        ),
        nullable=False,
        default=ResearchJobStatus.QUEUED,
        server_default=ResearchJobStatus.QUEUED.value,
    )

    current_stage: Mapped[ResearchStage | None] = mapped_column(
        Enum(
            ResearchStage,
            name="research_stage",
            native_enum=False,
            length=64,
            values_callable=_values,
        ),
        nullable=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
    )

    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    lease_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    request_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
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
