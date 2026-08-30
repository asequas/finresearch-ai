import uuid

from pydantic import BaseModel, ConfigDict, Field

from backend.models.research_job import ResearchJobStatus, ResearchStage


class ResearchCreateRequest(BaseModel):
    query: str = Field(min_length=1)
    company: str = Field(min_length=1, max_length=255)
    ticker: str = Field(min_length=1, max_length=20)


class ResearchJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    company: str
    ticker: str
    status: ResearchJobStatus
    current_stage: ResearchStage | None
    progress: int