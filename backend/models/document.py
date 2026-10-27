import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.document_chunk import DocumentChunk


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "ix_documents_source_type",
            "source_type",
        ),
        Index(
            "ix_documents_document_date",
            "document_date",
        ),
        Index(
            "ix_documents_company_form",
            "company_id",
            "form_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    form_type: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    accession_number: Mapped[str | None] = mapped_column(
        String(25),
        unique=True,
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    publisher: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Period of report for filings (e.g. fiscal year end for a 10-K).
    document_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    filed_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    content_hash: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )

    retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
