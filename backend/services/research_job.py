from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.research_job import ResearchJob,ResearchJobStatus
from backend.repositories.research_job import ResearchJobRepository
from backend.schemas.research import ResearchCreateRequest


class ResearchJobService:
    def __init__(self, repository: ResearchJobRepository):
        self.repository = repository

    def create_research_job(
        self,
        session: Session,
        *,
        user_id: UUID,
        request: ResearchCreateRequest,
    ) -> ResearchJob:
        return self.repository.create(
            session,
            user_id=user_id,
            query=request.query,
            company=request.company,
            ticker=request.ticker,
        )
    
    def get_research_job(
        self,
        session: Session,
        *,
        job_id: UUID,
    ) -> ResearchJob | None:
        return self.repository.get_by_id(
            session,
            job_id=job_id,
        )
    
    def update_status(
        self,
        session: Session,
        *,
        job_id: UUID,
        new_status: ResearchJobStatus,
    ) -> ResearchJob | None:
        job = self.repository.get_by_id(
            session,
            job_id=job_id,
        )

        if job is None:
            return None

        allowed_transitions = {
            ResearchJobStatus.QUEUED: {
                ResearchJobStatus.RUNNING,
            },
            ResearchJobStatus.RUNNING: {
                ResearchJobStatus.COMPLETED,
                ResearchJobStatus.FAILED,
            },
            ResearchJobStatus.COMPLETED: set(),
            ResearchJobStatus.FAILED: set(),
        }

        if new_status not in allowed_transitions[job.status]:
            raise ValueError(
                f"Invalid status transition: "
                f"{job.status.value} -> {new_status.value}"
            )

        return self.repository.update_status(
            session,
            job_id=job_id,
            status=new_status,
        )
    
    def update_progress(
        self,
        session: Session,
        *,
        job_id: UUID,
        progress: int,
    ) -> ResearchJob | None:
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")

        return self.repository.update_progress(
            session,
            job_id=job_id,
            progress=progress,
        )