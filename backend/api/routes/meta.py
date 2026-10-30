from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.core.config import settings
from backend.models.agent_run import AgentRun
from backend.models.research_job import ResearchJob, ResearchJobStatus

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])


class ModelInfo(BaseModel):
    fast: str
    strong: str
    embedding: str


class QueueInfo(BaseModel):
    queued: int
    running: int
    oldest_queued_seconds: float | None


class StageTiming(BaseModel):
    stage: str
    median_ms: int
    samples: int


class MetaResponse(BaseModel):
    version: str
    pipeline: str
    gemini_configured: bool
    sec_configured: bool
    models: ModelInfo
    lease_seconds: int
    max_attempts: int
    queue: QueueInfo
    stage_timings: list[StageTiming]
    reranker: str


@router.get("", response_model=MetaResponse)
def get_meta(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(ResearchJob.status, func.count())
            .where(ResearchJob.status.in_([ResearchJobStatus.QUEUED, ResearchJobStatus.RUNNING]))
            .group_by(ResearchJob.status)
        ).all()
    )
    oldest = db.scalar(
        select(func.extract("epoch", func.now() - func.min(ResearchJob.created_at))).where(
            ResearchJob.status == ResearchJobStatus.QUEUED, ResearchJob.run_after <= func.now()
        )
    )
    timings = db.execute(
        select(
            AgentRun.agent_name,
            func.percentile_cont(0.5).within_group(AgentRun.duration_ms),
            func.count(),
        )
        .where(AgentRun.status == "completed", AgentRun.duration_ms.is_not(None))
        .group_by(AgentRun.agent_name)
    ).all()
    return MetaResponse(
        version="0.2.0",
        pipeline=settings.pipeline,
        gemini_configured=bool(settings.gemini_api_key),
        sec_configured=bool(settings.sec_user_agent and "@" in settings.sec_user_agent),
        models=ModelInfo(
            fast=settings.gemini_fast_model, strong=settings.gemini_strong_model, embedding=settings.gemini_embedding_model
        ),
        lease_seconds=settings.worker_lease_seconds,
        max_attempts=settings.job_max_attempts,
        queue=QueueInfo(
            queued=counts.get(ResearchJobStatus.QUEUED, 0),
            running=counts.get(ResearchJobStatus.RUNNING, 0),
            oldest_queued_seconds=float(oldest) if oldest is not None else None,
        ),
        stage_timings=[StageTiming(stage=name, median_ms=int(median), samples=n) for name, median, n in timings],
        reranker=settings.reranker,
    )
