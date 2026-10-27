"""Persistence for research jobs, including the Postgres-backed queue (ADR 0001).

Repositories never commit. Every state change is a single conditional UPDATE
whose WHERE clause carries the expected state (and, for workers, the lease
token), so a stale or illegal transition updates zero rows instead of
corrupting the job.
"""
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from backend.models.research_job import ResearchJob, ResearchJobStatus, ResearchStage


def _seconds(value: float):
    return func.make_interval(0, 0, 0, 0, 0, 0, value)


class ResearchJobRepository:
    # ---- API-facing reads and writes -------------------------------------

    def create(
        self,
        session: Session,
        *,
        user_id: UUID,
        query: str,
        company: str,
        ticker: str,
        idempotency_key: str | None = None,
        request_fingerprint: str | None = None,
        max_attempts: int = 3,
    ) -> ResearchJob:
        job = ResearchJob(
            user_id=user_id,
            query=query,
            company=company,
            ticker=ticker,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            max_attempts=max_attempts,
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

    def get_for_user(
        self,
        session: Session,
        *,
        job_id: UUID,
        user_id: UUID,
    ) -> ResearchJob | None:
        return session.scalar(
            select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id)
        )

    def get_by_idempotency_key(
        self,
        session: Session,
        *,
        user_id: UUID,
        idempotency_key: str,
    ) -> ResearchJob | None:
        return session.scalar(
            select(ResearchJob).where(
                ResearchJob.user_id == user_id,
                ResearchJob.idempotency_key == idempotency_key,
            )
        )

    def list_for_user(
        self,
        session: Session,
        *,
        user_id: UUID,
        limit: int,
        before: tuple[datetime, UUID] | None = None,
        status: ResearchJobStatus | None = None,
        ticker: str | None = None,
    ) -> list[ResearchJob]:
        statement = select(ResearchJob).where(ResearchJob.user_id == user_id)

        if status is not None:
            statement = statement.where(ResearchJob.status == status)
        if ticker is not None:
            statement = statement.where(ResearchJob.ticker == ticker)
        if before is not None:
            created_at, job_id = before
            statement = statement.where(
                or_(
                    ResearchJob.created_at < created_at,
                    and_(ResearchJob.created_at == created_at, ResearchJob.id < job_id),
                )
            )

        statement = statement.order_by(ResearchJob.created_at.desc(), ResearchJob.id.desc()).limit(limit)
        return list(session.scalars(statement))

    def cancel_queued(self, session: Session, *, job_id: UUID) -> bool:
        result = session.execute(
            update(ResearchJob)
            .where(ResearchJob.id == job_id, ResearchJob.status == ResearchJobStatus.QUEUED)
            .values(
                status=ResearchJobStatus.CANCELLED,
                completed_at=func.now(),
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    def request_cancel_running(self, session: Session, *, job_id: UUID) -> bool:
        result = session.execute(
            update(ResearchJob)
            .where(ResearchJob.id == job_id, ResearchJob.status == ResearchJobStatus.RUNNING)
            .values(cancel_requested=True, updated_at=func.now())
        )
        return result.rowcount == 1

    def requeue_for_retry(self, session: Session, *, job_id: UUID) -> bool:
        result = session.execute(
            update(ResearchJob)
            .where(
                ResearchJob.id == job_id,
                ResearchJob.status.in_([ResearchJobStatus.FAILED, ResearchJobStatus.CANCELLED]),
            )
            .values(
                status=ResearchJobStatus.QUEUED,
                attempts=0,
                run_after=func.now(),
                error_message=None,
                cancel_requested=False,
                completed_at=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    # ---- Worker-facing queue operations ----------------------------------

    def claim_next(self, session: Session, *, lease_seconds: float) -> ResearchJob | None:
        """Atomically claim one queued job, or one whose lease expired with attempts left."""
        claimable = (
            select(ResearchJob.id)
            .where(
                or_(
                    and_(
                        ResearchJob.status == ResearchJobStatus.QUEUED,
                        ResearchJob.run_after <= func.now(),
                    ),
                    and_(
                        ResearchJob.status == ResearchJobStatus.RUNNING,
                        ResearchJob.lease_expires_at < func.now(),
                        ResearchJob.attempts < ResearchJob.max_attempts,
                    ),
                )
            )
            .order_by(ResearchJob.run_after, ResearchJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )

        claimed_id = session.execute(
            update(ResearchJob)
            .where(ResearchJob.id == claimable)
            .values(
                status=ResearchJobStatus.RUNNING,
                lease_token=uuid.uuid4(),
                lease_expires_at=func.now() + _seconds(lease_seconds),
                attempts=ResearchJob.attempts + 1,
                started_at=func.coalesce(ResearchJob.started_at, func.now()),
                updated_at=func.now(),
            )
            .returning(ResearchJob.id)
        ).scalar_one_or_none()

        if claimed_id is None:
            return None

        return session.get(ResearchJob, claimed_id, populate_existing=True)

    def reap_exhausted(self, session: Session) -> list[UUID]:
        """Fail running jobs whose lease expired and that have no attempts left."""
        return list(
            session.scalars(
                update(ResearchJob)
                .where(
                    ResearchJob.status == ResearchJobStatus.RUNNING,
                    ResearchJob.lease_expires_at < func.now(),
                    ResearchJob.attempts >= ResearchJob.max_attempts,
                )
                .values(
                    status=ResearchJobStatus.FAILED,
                    error_message=(
                        "The research worker stopped responding repeatedly while running this job."
                    ),
                    completed_at=func.now(),
                    lease_token=None,
                    lease_expires_at=None,
                    updated_at=func.now(),
                )
                .returning(ResearchJob.id)
            )
        )

    def _fenced(self, job_id: UUID, lease_token: UUID):
        return update(ResearchJob).where(
            ResearchJob.id == job_id,
            ResearchJob.status == ResearchJobStatus.RUNNING,
            ResearchJob.lease_token == lease_token,
        )

    def heartbeat(
        self, session: Session, *, job_id: UUID, lease_token: UUID, lease_seconds: float
    ) -> bool | None:
        """Extend the lease. Returns cancel_requested, or None if the lease was lost."""
        return session.execute(
            self._fenced(job_id, lease_token)
            .values(lease_expires_at=func.now() + _seconds(lease_seconds), updated_at=func.now())
            .returning(ResearchJob.cancel_requested)
        ).scalar_one_or_none()

    def assert_lease(self, session: Session, *, job_id: UUID, lease_token: UUID) -> bool:
        """Lock the job row for the current transaction if we still own it."""
        return (
            session.scalar(
                select(ResearchJob.id)
                .where(
                    ResearchJob.id == job_id,
                    ResearchJob.status == ResearchJobStatus.RUNNING,
                    ResearchJob.lease_token == lease_token,
                )
                .with_for_update()
            )
            is not None
        )

    def set_stage(
        self,
        session: Session,
        *,
        job_id: UUID,
        lease_token: UUID,
        stage: ResearchStage,
        progress: int,
    ) -> bool:
        result = session.execute(
            self._fenced(job_id, lease_token).values(
                current_stage=stage,
                progress=func.greatest(ResearchJob.progress, progress),
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    def complete(self, session: Session, *, job_id: UUID, lease_token: UUID) -> bool:
        result = session.execute(
            self._fenced(job_id, lease_token).values(
                status=ResearchJobStatus.COMPLETED,
                progress=100,
                current_stage=None,
                error_message=None,
                completed_at=func.now(),
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    def schedule_retry(
        self,
        session: Session,
        *,
        job_id: UUID,
        lease_token: UUID,
        error_message: str,
        delay_seconds: float,
    ) -> bool:
        result = session.execute(
            self._fenced(job_id, lease_token).values(
                status=ResearchJobStatus.QUEUED,
                error_message=error_message,
                run_after=func.now() + _seconds(delay_seconds),
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    def fail(
        self, session: Session, *, job_id: UUID, lease_token: UUID, error_message: str
    ) -> bool:
        result = session.execute(
            self._fenced(job_id, lease_token).values(
                status=ResearchJobStatus.FAILED,
                error_message=error_message,
                completed_at=func.now(),
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    def mark_cancelled(self, session: Session, *, job_id: UUID, lease_token: UUID) -> bool:
        result = session.execute(
            self._fenced(job_id, lease_token).values(
                status=ResearchJobStatus.CANCELLED,
                completed_at=func.now(),
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1

    def release(self, session: Session, *, job_id: UUID, lease_token: UUID) -> bool:
        """Give a job back on graceful shutdown without spending an attempt."""
        result = session.execute(
            self._fenced(job_id, lease_token).values(
                status=ResearchJobStatus.QUEUED,
                attempts=func.greatest(ResearchJob.attempts - 1, 0),
                run_after=func.now(),
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        return result.rowcount == 1
