"""Worker-facing queue operations. Each call is its own short, committed transaction."""
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models.agent_run import AgentRun
from backend.models.research_job import ResearchJob, ResearchStage
from backend.repositories.research_job import ResearchJobRepository


class JobQueueService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        repository: ResearchJobRepository | None = None,
    ):
        self.session_factory = session_factory
        self.repository = repository or ResearchJobRepository()

    def claim_next(self, *, lease_seconds: float) -> ResearchJob | None:
        with self.session_factory() as session:
            job = self.repository.claim_next(session, lease_seconds=lease_seconds)
            session.commit()
            return job

    def reap_exhausted(self) -> list[UUID]:
        with self.session_factory() as session:
            reaped = self.repository.reap_exhausted(session)
            session.commit()
            return reaped

    def heartbeat(self, job_id: UUID, lease_token: UUID, *, lease_seconds: float) -> bool | None:
        with self.session_factory() as session:
            result = self.repository.heartbeat(
                session, job_id=job_id, lease_token=lease_token, lease_seconds=lease_seconds
            )
            session.commit()
            return result

    def _fenced_call(self, method: str, job_id: UUID, lease_token: UUID, **kwargs) -> bool:
        with self.session_factory() as session:
            ok = getattr(self.repository, method)(
                session, job_id=job_id, lease_token=lease_token, **kwargs
            )
            session.commit()
            return ok

    def set_stage(self, job_id: UUID, lease_token: UUID, *, stage: ResearchStage, progress: int) -> bool:
        return self._fenced_call("set_stage", job_id, lease_token, stage=stage, progress=progress)

    def complete(self, job_id: UUID, lease_token: UUID) -> bool:
        return self._fenced_call("complete", job_id, lease_token)

    def schedule_retry(
        self, job_id: UUID, lease_token: UUID, *, error_message: str, delay_seconds: float
    ) -> bool:
        return self._fenced_call(
            "schedule_retry",
            job_id,
            lease_token,
            error_message=error_message,
            delay_seconds=delay_seconds,
        )

    def fail(self, job_id: UUID, lease_token: UUID, *, error_message: str) -> bool:
        return self._fenced_call("fail", job_id, lease_token, error_message=error_message)

    def mark_cancelled(self, job_id: UUID, lease_token: UUID) -> bool:
        return self._fenced_call("mark_cancelled", job_id, lease_token)

    def release(self, job_id: UUID, lease_token: UUID) -> bool:
        return self._fenced_call("release", job_id, lease_token)

    # ---- Stage checkpoints (agent_runs) ----------------------------------

    def completed_stages(self, job_id: UUID) -> set[str]:
        with self.session_factory() as session:
            return set(
                session.scalars(
                    select(AgentRun.agent_name).where(
                        AgentRun.research_job_id == job_id, AgentRun.status == "completed"
                    )
                )
            )

    def start_stage_run(
        self, job_id: UUID, lease_token: UUID, *, stage: ResearchStage, attempt: int, agent_name: str | None = None
    ) -> UUID | None:
        """Record a stage start; None if this worker no longer owns the job.

        `agent_name` names a run inside a stage (e.g. the critic); it defaults to the stage itself.
        """
        with self.session_factory() as session:
            if not self.repository.assert_lease(session, job_id=job_id, lease_token=lease_token):
                return None
            run = AgentRun(research_job_id=job_id, agent_name=agent_name or stage.value, status="running", attempt=attempt)
            session.add(run)
            session.commit()
            return run.id

    def finish_stage_run(
        self,
        run_id: UUID,
        *,
        status: str,
        started: datetime,
        error_message: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: Decimal = Decimal("0"),
        metadata: dict | None = None,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(
                    status=status,
                    completed_at=completed_at,
                    duration_ms=int((completed_at - started).total_seconds() * 1000),
                    error_message=error_message,
                    model=model,
                    input_tokens=input_tokens or None,
                    output_tokens=output_tokens or None,
                    estimated_cost=estimated_cost or None,
                    extra_metadata=metadata or None,
                )
            )
            session.commit()
