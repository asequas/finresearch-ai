import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class LlmCall(Base):
    """The cost ledger: one row per model call that returned a response (ADR 0009).

    Rows outlive their job (ON DELETE SET NULL): money spent stays spent. `cost_usd` is the list price at the time
    of the call; `billable` says whether the project was on a paid tier then (free-tier calls cost nothing).
    """

    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint("operation IN ('generate', 'embed')", name="ck_llm_calls_operation"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND cached_tokens >= 0 AND thinking_tokens >= 0",
            name="ck_llm_calls_tokens",
        ),
        Index("ix_llm_calls_created_at", "created_at"),
        Index("ix_llm_calls_research_job_id", "research_job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # job, chat, other
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # includes thinking
    thinking_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)  # NULL = model not priced
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # token counts estimated
