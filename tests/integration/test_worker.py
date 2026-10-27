"""Worker behaviour end to end with fake stages (Phase 3 acceptance)."""
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field

from sqlalchemy import select, text

from backend.core.database import SessionLocal
from backend.models.agent_run import AgentRun
from backend.models.research_job import ResearchJob, ResearchJobStatus, ResearchStage
from backend.pipeline.base import JobContext, PermanentError, RetryableError
from backend.pipeline.stub import SleepStage
from backend.worker.main import Worker


@dataclass
class ScriptedStage:
    """Fails the first `failures` times it runs, then succeeds."""

    name: ResearchStage
    weight: int = 1
    failures: int = 0
    error: type[Exception] = RetryableError
    calls: list = field(default_factory=list)

    def run(self, ctx: JobContext) -> None:
        self.calls.append(ctx.attempt)
        if len(self.calls) <= self.failures:
            raise self.error(f"{self.name.value} failed")


def _worker(stages, **kwargs) -> Worker:
    return Worker(stages_factory=lambda: stages, lease_seconds=kwargs.pop("lease_seconds", 30), retry_base_seconds=0, **kwargs)


def _get(job_id) -> ResearchJob:
    with SessionLocal() as session:
        return session.get(ResearchJob, job_id)


def _stage_runs(job_id) -> list[AgentRun]:
    with SessionLocal() as session:
        return list(
            session.scalars(select(AgentRun).where(AgentRun.research_job_id == job_id).order_by(AgentRun.started_at))
        )


def test_worker_runs_all_stages_and_completes(make_job):
    job = make_job()
    stages = [ScriptedStage(name=stage) for stage in list(ResearchStage)[:3]]

    assert _worker(stages).run_once() is True

    finished = _get(job.id)
    assert finished.status == ResearchJobStatus.COMPLETED
    assert finished.progress == 100
    runs = _stage_runs(job.id)
    assert [run.agent_name for run in runs] == [stage.name.value for stage in stages]
    assert all(run.status == "completed" and run.duration_ms is not None for run in runs)


def test_run_once_returns_false_when_idle():
    assert _worker([]).run_once() is False


def test_retryable_failure_retries_and_resumes_from_checkpoint(make_job):
    job = make_job()
    first = ScriptedStage(name=ResearchStage.RESOLVING_COMPANY)
    flaky = ScriptedStage(name=ResearchStage.FETCHING_FILINGS, failures=1)
    worker = _worker([first, flaky])

    worker.run_once()
    after_failure = _get(job.id)
    assert after_failure.status == ResearchJobStatus.QUEUED
    assert "fetching_filings failed" in after_failure.error_message

    worker.run_once()

    assert _get(job.id).status == ResearchJobStatus.COMPLETED
    assert first.calls == [1]  # not re-run on attempt 2
    assert flaky.calls == [1, 2]


def test_permanent_failure_fails_immediately(make_job):
    job = make_job()
    stage = ScriptedStage(name=ResearchStage.RESOLVING_COMPANY, failures=1, error=PermanentError)

    _worker([stage]).run_once()

    failed = _get(job.id)
    assert failed.status == ResearchJobStatus.FAILED
    assert failed.error_message == "resolving_company failed"
    assert failed.attempts == 1


def test_gives_up_after_max_attempts(make_job):
    job = make_job(max_attempts=2)
    stage = ScriptedStage(name=ResearchStage.RESOLVING_COMPANY, failures=5)
    worker = _worker([stage])

    worker.run_once()
    worker.run_once()

    failed = _get(job.id)
    assert failed.status == ResearchJobStatus.FAILED
    assert failed.error_message.startswith("Gave up after 2 attempts")
    assert worker.run_once() is False


def test_cancel_requested_stops_at_stage_boundary(make_job):
    job = make_job()

    class CancelDuring(ScriptedStage):
        def run(self, ctx):
            super().run(ctx)
            ctx.cancel_event.set()

    later = ScriptedStage(name=ResearchStage.FETCHING_FILINGS)
    _worker([CancelDuring(name=ResearchStage.RESOLVING_COMPANY), later]).run_once()

    assert _get(job.id).status == ResearchJobStatus.CANCELLED
    assert later.calls == []


def test_duplicate_delivery_after_completion_is_harmless(make_job):
    job = make_job()
    stage = ScriptedStage(name=ResearchStage.RESOLVING_COMPANY)
    worker = _worker([stage])
    worker.run_once()

    # A redelivery of an already-completed job: nothing is claimable, nothing re-runs.
    assert worker.run_once() is False
    assert stage.calls == [1]
    assert _get(job.id).status == ResearchJobStatus.COMPLETED


def test_lost_lease_mid_stage_abandons_without_writes(make_job):
    job = make_job()

    class StolenDuring(ScriptedStage):
        def run(self, ctx):
            with SessionLocal() as session:  # another worker reclaims the job
                session.execute(
                    text("UPDATE research_jobs SET lease_token = gen_random_uuid() WHERE id = :id"), {"id": ctx.job_id}
                )
                session.commit()
            with ctx.transaction():
                raise AssertionError("fenced transaction must not open")

    _worker([StolenDuring(name=ResearchStage.RESOLVING_COMPANY)]).run_once()

    abandoned = _get(job.id)
    assert abandoned.status == ResearchJobStatus.RUNNING  # left for the new owner
    assert abandoned.error_message is None


def test_heartbeat_keeps_long_stage_alive(make_job):
    job = make_job()
    _worker([SleepStage(name=ResearchStage.ANALYZING, seconds=2.5)], lease_seconds=1.5).run_once()

    assert _get(job.id).status == ResearchJobStatus.COMPLETED
    assert _get(job.id).attempts == 1


def test_worker_crash_is_recovered_by_another_worker(make_job):
    """kill -9 a real worker process mid-job; a second worker finishes it after the lease expires."""
    job = make_job()
    env = {
        **os.environ,
        "PIPELINE": "stub",
        "STUB_STAGE_SECONDS": "5",
        "WORKER_LEASE_SECONDS": "2",
        "WORKER_POLL_INTERVAL_SECONDS": "0.1",
    }
    process = subprocess.Popen([sys.executable, "-m", "backend.worker.main"], env=env)
    try:
        deadline = time.monotonic() + 15
        while _get(job.id).status != ResearchJobStatus.RUNNING:
            assert time.monotonic() < deadline, "worker never claimed the job"
            time.sleep(0.1)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()

    crashed = _get(job.id)
    assert crashed.status == ResearchJobStatus.RUNNING
    time.sleep(2.5)  # lease expires

    stage = ScriptedStage(name=ResearchStage.RESOLVING_COMPANY)
    assert _worker([stage]).run_once() is True

    recovered = _get(job.id)
    assert recovered.status == ResearchJobStatus.COMPLETED
    assert recovered.attempts == 2


def test_sigterm_releases_job_for_another_worker(make_job):
    job = make_job()
    env = {**os.environ, "PIPELINE": "stub", "STUB_STAGE_SECONDS": "5", "WORKER_POLL_INTERVAL_SECONDS": "0.1"}
    process = subprocess.Popen([sys.executable, "-m", "backend.worker.main"], env=env)
    try:
        deadline = time.monotonic() + 15
        while _get(job.id).status != ResearchJobStatus.RUNNING:
            assert time.monotonic() < deadline
            time.sleep(0.1)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()

    released = _get(job.id)
    assert released.status == ResearchJobStatus.QUEUED
    assert released.attempts == 0
