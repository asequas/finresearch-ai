"""API-facing research job operations. The service owns every transaction."""
import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.agent_run import AgentRun
from backend.models.report import Report
from backend.models.research_job import ResearchJob, ResearchJobStatus
from backend.repositories.research_job import ResearchJobRepository
from backend.schemas.research import (
    ResearchCreateRequest,
    ResearchJobDetailResponse,
    ResearchJobListResponse,
    ResearchJobResponse,
    StageRunResponse,
)
from backend.costs.budget import budget_status
from backend.services.errors import BadRequestError, ConflictError, InvalidStateError, LimitReachedError, NotFoundError


def fingerprint(request: ResearchCreateRequest) -> str:
    canonical = json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def encode_cursor(job: ResearchJob) -> str:
    raw = f"{job.created_at.isoformat()}|{job.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        created_at, job_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(created_at), UUID(job_id)
    except Exception as exc:
        raise BadRequestError("Invalid pagination cursor") from exc


class ResearchJobService:
    def __init__(self, repository: ResearchJobRepository):
        self.repository = repository

    def submit(
        self,
        session: Session,
        *,
        user_id: UUID,
        request: ResearchCreateRequest,
        idempotency_key: str | None = None,
    ) -> ResearchJob:
        """Create a queued job. Committing it is what enqueues it (ADR 0001, 0003)."""
        request_fingerprint = fingerprint(request)

        if idempotency_key is not None:
            existing = self.repository.get_by_idempotency_key(
                session, user_id=user_id, idempotency_key=idempotency_key
            )
            if existing is not None:
                return self._replay(existing, request_fingerprint)

        # A spent budget refuses new work up front (a replay above still returns the existing job).
        if settings.gemini_billing == "paid" and (reason := budget_status(session).blocked_reason):
            raise LimitReachedError(reason)

        try:
            job = self.repository.create(
                session,
                user_id=user_id,
                query=request.query,
                company=request.company,
                ticker=request.ticker,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                max_attempts=settings.job_max_attempts,
            )
            session.commit()
        except IntegrityError:
            # Lost the race against a concurrent request with the same key.
            session.rollback()
            if idempotency_key is None:
                raise
            existing = self.repository.get_by_idempotency_key(
                session, user_id=user_id, idempotency_key=idempotency_key
            )
            if existing is None:
                raise
            return self._replay(existing, request_fingerprint)

        session.refresh(job)
        return job

    @staticmethod
    def _replay(existing: ResearchJob, request_fingerprint: str) -> ResearchJob:
        if existing.request_fingerprint != request_fingerprint:
            raise ConflictError("Idempotency-Key was already used with a different request")
        return existing

    def get_research_job(self, session: Session, *, job_id: UUID, user_id: UUID) -> ResearchJob:
        job = self.repository.get_for_user(session, job_id=job_id, user_id=user_id)
        if job is None:
            # Another user's job is indistinguishable from a missing one.
            raise NotFoundError("Research job not found")
        return job

    def get_detail(self, session: Session, *, job_id: UUID, user_id: UUID) -> ResearchJobDetailResponse:
        job = self.get_research_job(session, job_id=job_id, user_id=user_id)
        stages = session.scalars(
            select(AgentRun)
            .where(AgentRun.research_job_id == job.id)
            .order_by(AgentRun.started_at, AgentRun.id)
        )
        detail = ResearchJobDetailResponse.model_validate(job)
        detail.has_report = self._has_report(session, job.id)
        detail.stages = [StageRunResponse.model_validate(stage) for stage in stages]
        return detail

    def list_jobs(
        self,
        session: Session,
        *,
        user_id: UUID,
        limit: int,
        cursor: str | None = None,
        status: ResearchJobStatus | None = None,
        ticker: str | None = None,
    ) -> ResearchJobListResponse:
        jobs = self.repository.list_for_user(
            session,
            user_id=user_id,
            limit=limit + 1,
            before=decode_cursor(cursor) if cursor else None,
            status=status,
            ticker=ticker.strip().upper() if ticker else None,
        )
        page = jobs[:limit]
        with_reports = self._job_ids_with_reports(session, [job.id for job in page])
        items = []
        for job in page:
            item = ResearchJobResponse.model_validate(job)
            item.has_report = job.id in with_reports
            items.append(item)
        return ResearchJobListResponse(
            items=items,
            next_cursor=encode_cursor(page[-1]) if len(jobs) > limit else None,
        )

    def cancel(self, session: Session, *, job_id: UUID, user_id: UUID) -> ResearchJob:
        job = self.get_research_job(session, job_id=job_id, user_id=user_id)
        if not (
            self.repository.cancel_queued(session, job_id=job.id)
            or self.repository.request_cancel_running(session, job_id=job.id)
        ):
            session.rollback()
            raise InvalidStateError(f"A {job.status.value} job cannot be cancelled")
        session.commit()
        session.refresh(job)
        return job

    def retry(self, session: Session, *, job_id: UUID, user_id: UUID) -> ResearchJob:
        job = self.get_research_job(session, job_id=job_id, user_id=user_id)
        if not self.repository.requeue_for_retry(session, job_id=job.id):
            session.rollback()
            raise InvalidStateError(f"A {job.status.value} job cannot be retried")
        session.commit()
        session.refresh(job)
        return job

    @staticmethod
    def _has_report(session: Session, job_id: UUID) -> bool:
        return bool(session.scalar(select(exists().where(Report.research_job_id == job_id))))

    @staticmethod
    def _job_ids_with_reports(session: Session, job_ids: list[UUID]) -> set[UUID]:
        if not job_ids:
            return set()
        return set(
            session.scalars(select(Report.research_job_id).where(Report.research_job_id.in_(job_ids)))
        )
