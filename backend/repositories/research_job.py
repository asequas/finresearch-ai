from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.research_job import ResearchJob, ResearchJobStatus


class ResearchJobRepository:
    def create(
        self,
        session: Session,
        *,
        user_id: UUID,
        query: str,
        company: str,
        ticker: str,
    ) -> ResearchJob:
        job = ResearchJob(
            user_id=user_id,
            query=query,
            company=company,
            ticker=ticker,
        )

        session.add(job)
        session.flush()

        return job
    
    def get_by_id(
        self,
        session: Session,
        *,
        job_id: UUID,
    ) -> ResearchJob | None:
        return session.get(ResearchJob, job_id)
    
    def update_status(
        self,
        session: Session,
        *,
        job_id: UUID,
        status: ResearchJobStatus,
    ) -> ResearchJob | None:
        job = self.get_by_id(session, job_id=job_id)

        if job is None:
            return None

        job.status = status
        session.flush()

        return job
    
    def update_progress(
        self,
        session: Session,
        *,
        job_id: UUID,
        progress: int,
    ) -> ResearchJob | None:
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")

        job = self.get_by_id(session, job_id=job_id)

        if job is None:
            return None

        job.progress = progress
        session.flush()

        return job