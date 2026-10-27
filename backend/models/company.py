import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Company(Base):
    """An SEC registrant, keyed by CIK. Shared across research jobs."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cik: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sic: Mapped[str | None] = mapped_column(String(4), nullable=True)
    sic_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fiscal_year_end: Mapped[str | None] = mapped_column(String(4), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
