import uuid
from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.research_job import ResearchJobStatus, ResearchStage

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class ResearchCreateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    company: str = Field(min_length=1, max_length=255)
    ticker: str = Field(min_length=1, max_length=10)

    @field_validator("query", "company", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("ticker", mode="before")
    @classmethod
    def normalise_ticker(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("ticker")
    @classmethod
    def check_ticker(cls, value: str) -> str:
        if not TICKER_PATTERN.match(value):
            raise ValueError("ticker must look like AAPL or BRK.B")
        return value


class ResearchJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    company: str
    ticker: str
    status: ResearchJobStatus
    current_stage: ResearchStage | None
    progress: int
    attempts: int
    max_attempts: int
    error_message: str | None
    cancel_requested: bool
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    has_report: bool = False


class StageRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str = Field(validation_alias="agent_name")
    status: str
    attempt: int
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None


class ResearchJobDetailResponse(ResearchJobResponse):
    stages: list[StageRunResponse] = []


class ResearchJobListResponse(BaseModel):
    items: list[ResearchJobResponse]
    next_cursor: str | None
