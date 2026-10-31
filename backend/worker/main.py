"""Research worker: claims jobs from Postgres and runs the pipeline (ADR 0001).

Run with:  python -m backend.worker.main
"""
import logging
import random
import signal
import threading
from collections.abc import Callable, Sequence

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models.research_job import ResearchJob
from backend.pipeline.base import (
    CancelRequested,
    JobContext,
    LeaseLost,
    PermanentError,
    ProviderBusyError,
    ShutdownRequested,
    Stage,
)
from backend.pipeline.runner import run_pipeline
from backend.services.job_queue import JobQueueService

logger = logging.getLogger("finresearch.worker")


def backoff_seconds(attempt: int, base: float) -> float:
    """Exponential backoff with jitter: base, 2*base, 4*base ... (±20%)."""
    return base * (2 ** (attempt - 1)) * random.uniform(0.8, 1.2)


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, PermanentError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"[:1000]


class Heartbeat(threading.Thread):
    """Extends the lease every lease/3 seconds and relays cancel / lease-loss to the job."""

    def __init__(self, queue: JobQueueService, ctx: JobContext, lease_seconds: float):
        super().__init__(daemon=True, name=f"heartbeat-{ctx.job_id}")
        self.queue = queue
        self.ctx = ctx
        self.lease_seconds = lease_seconds
        self.stopped = threading.Event()

    def run(self) -> None:
        while not self.stopped.wait(self.lease_seconds / 3):
            try:
                cancel_requested = self.queue.heartbeat(
                    self.ctx.job_id, self.ctx.lease_token, lease_seconds=self.lease_seconds
                )
            except Exception:
                logger.exception("heartbeat failed for job %s; will retry", self.ctx.job_id)
                continue
            if cancel_requested is None:
                logger.warning("job %s: lease lost", self.ctx.job_id)
                self.ctx.lease_lost_event.set()
                return
            if cancel_requested:
                self.ctx.cancel_event.set()

    def stop(self) -> None:
        self.stopped.set()


class Worker:
    def __init__(
        self,
        *,
        stages_factory: Callable[[], Sequence[Stage]],
        session_factory=SessionLocal,
        lease_seconds: float = settings.worker_lease_seconds,
        poll_interval: float = settings.worker_poll_interval_seconds,
        retry_base_seconds: float = settings.job_retry_base_seconds,
        busy_retry_base_seconds: float = settings.job_busy_retry_base_seconds,
    ):
        self.stages_factory = stages_factory
        self.session_factory = session_factory
        self.queue = JobQueueService(session_factory)
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self.retry_base_seconds = retry_base_seconds
        self.busy_retry_base_seconds = busy_retry_base_seconds
        self.shutdown_event = threading.Event()

    def run_forever(self) -> None:
        logger.info("worker started (lease=%ss, poll=%ss)", self.lease_seconds, self.poll_interval)
        while not self.shutdown_event.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("worker loop error; backing off")
                worked = False
            if not worked:
                self.shutdown_event.wait(self.poll_interval)
        logger.info("worker stopped")

    def run_once(self) -> bool:
        """Reap exhausted jobs, then claim and execute at most one job."""
        for job_id in self.queue.reap_exhausted():
            logger.warning("job %s: failed after exhausting attempts", job_id)

        job = self.queue.claim_next(lease_seconds=self.lease_seconds)
        if job is None:
            return False
        self.execute(job)
        return True

    def execute(self, job: ResearchJob) -> None:
        ctx = JobContext(
            job_id=job.id,
            lease_token=job.lease_token,
            attempt=job.attempts,
            query=job.query,
            company=job.company,
            ticker=job.ticker,
            session_factory=self.session_factory,
            shutdown_event=self.shutdown_event,
        )
        if job.cancel_requested:
            ctx.cancel_event.set()

        heartbeat = Heartbeat(self.queue, ctx, self.lease_seconds)
        heartbeat.start()
        logger.info("job %s: claimed (attempt %d/%d)", job.id, job.attempts, job.max_attempts)
        try:
            run_pipeline(ctx, self.stages_factory(), self.queue)
            if not self.queue.complete(job.id, ctx.lease_token):
                raise LeaseLost(f"Lease lost for job {job.id} before completion")
            logger.info("job %s: completed", job.id)
        except LeaseLost:
            logger.warning("job %s: abandoned, another worker owns it", job.id)
        except CancelRequested:
            self.queue.mark_cancelled(job.id, ctx.lease_token)
            logger.info("job %s: cancelled", job.id)
        except ShutdownRequested:
            self.queue.release(job.id, ctx.lease_token)
            logger.info("job %s: released for another worker (shutdown)", job.id)
        except PermanentError as exc:
            self.queue.fail(job.id, ctx.lease_token, error_message=describe_error(exc))
            logger.warning("job %s: failed permanently: %s", job.id, exc)
        except Exception as exc:
            message = describe_error(exc)
            if job.attempts < job.max_attempts:
                delay = (
                    min(backoff_seconds(job.attempts, self.busy_retry_base_seconds), 600)
                    if isinstance(exc, ProviderBusyError)
                    else backoff_seconds(job.attempts, self.retry_base_seconds)
                )
                self.queue.schedule_retry(
                    job.id, ctx.lease_token, error_message=message, delay_seconds=delay
                )
                logger.warning("job %s: retry in %.0fs after %s", job.id, delay, message)
            else:
                self.queue.fail(
                    job.id,
                    ctx.lease_token,
                    error_message=f"Gave up after {job.attempts} attempts. Last error: {message}",
                )
                logger.error("job %s: failed after %d attempts: %s", job.id, job.attempts, message)
        finally:
            heartbeat.stop()


def default_stages() -> Sequence[Stage]:
    if settings.pipeline == "stub":
        from backend.pipeline.stub import stub_stages

        return stub_stages()
    from backend.pipeline.research import research_stages

    return research_stages(agentic=settings.pipeline != "linear")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    worker = Worker(stages_factory=default_stages)

    def request_shutdown(signum, _frame):
        logger.info("signal %s received; finishing the current stage then stopping", signum)
        worker.shutdown_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    worker.run_forever()


if __name__ == "__main__":
    main()
