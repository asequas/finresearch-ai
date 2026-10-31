import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ReportChatMessage(Base):
    """One turn of the "Ask the analyst" conversation about a finished report (ADR 0008).

    This table is the record of the conversation; the chat agent is rebuilt from it on every turn,
    so there is no second copy of the history in a checkpointer.
    """

    __tablename__ = "report_chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_report_chat_messages_role"),
        Index("ix_report_chat_messages_job_created", "research_job_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{handle, quote, verified, document_id, chunk_id, section, form, period, url}]
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{tool, input, summary, ms}]: what the agent looked at before answering
    tool_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
