import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ResearchJobDocument(Base):
    """Which filings a job used. Documents are shared; this records the job's selection."""

    __tablename__ = "research_job_documents"
    __table_args__ = (Index("ix_research_job_documents_document_id", "document_id"),)

    research_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    # "primary" for the latest 10-K, "supplementary" for a newer 10-Q
    role: Mapped[str] = mapped_column(String(32), nullable=False)
