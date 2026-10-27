import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.document import Document
    from backend.models.document_chunk import DocumentChunk
    from backend.models.claim import Claim


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        Index(
            "ix_evidence_document_id",
            "document_id",
        ),
        Index(
            "ix_evidence_document_chunk_id",
            "document_chunk_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )

    excerpt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    quote_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    claims: Mapped[list["Claim"]] = relationship(
        secondary="claim_evidence",
        back_populates="evidence",
    )