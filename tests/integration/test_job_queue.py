"""Queue semantics from ADR 0001/0002: atomic claims, fencing, retries, recovery."""
import threading

from sqlalchemy import text

from backend.core.database import SessionLocal
from backend.models.research_job import ResearchJob, ResearchJobStatus, ResearchStage
from backend.services.job_queue import JobQueueService

queue = JobQueueService(SessionLocal)


def _get(job_id) -> ResearchJob:
    with SessionLocal() as session:
        return session.get(ResearchJob, job_id)


def _expire_lease(job_id) -> None:
    with SessionLocal() as session:
        session.execute(
            text("UPDATE research_jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id"),
            {"id": job_id},
        )
        session.commit()


def test_claim_sets_lease_attempt_and_started_at(make_job):
    job = make_job()

    claimed = queue.claim_next(lease_seconds=60)

    assert claimed.id == job.id
    assert claimed.status == ResearchJobStatus.RUNNING
    assert claimed.lease_token is not None
    assert claimed.lease_expires_at > claimed.started_at
    assert claimed.attempts == 1


def test_claim_returns_none_when_queue_empty():
    assert queue.claim_next(lease_seconds=60) is None


def test_concurrent_claimers_get_exactly_one_job(make_job):
    make_job()
    barrier, results = threading.Barrier(10), []

    def claim():
        barrier.wait()
        results.append(queue.claim_next(lease_seconds=60))

    threads = [threading.Thread(target=claim) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len([job for job in results if job is not None]) == 1


def test_concurrent_claimers_get_distinct_jobs(make_job):
    jobs = {make_job().id for _ in range(5)}
    barrier, claimed = threading.Barrier(5), []

    def claim():
        barrier.wait()
        claimed.append(queue.claim_next(lease_seconds=60).id)

    threads = [threading.Thread(target=claim) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(claimed) == sorted(jobs)


def test_job_scheduled_in_future_is_not_claimed(make_job):
    job = make_job()
    with SessionLocal() as session:
        session.execute(
            text("UPDATE research_jobs SET run_after = now() + interval '1 hour' WHERE id = :id"), {"id": job.id}
        )
        session.commit()

    assert queue.claim_next(lease_seconds=60) is None


def test_expired_lease_is_reclaimed_with_new_token(make_job):
    make_job()
    first = queue.claim_next(lease_seconds=60)
    _expire_lease(first.id)

    second = queue.claim_next(lease_seconds=60)

    assert second.id == first.id
    assert second.lease_token != first.lease_token
    assert second.attempts == 2


def test_zombie_worker_writes_are_fenced(make_job):
    make_job()
    zombie = queue.claim_next(lease_seconds=60)
    _expire_lease(zombie.id)
    owner = queue.claim_next(lease_seconds=60)

    assert queue.set_stage(zombie.id, zombie.lease_token, stage=ResearchStage.ANALYZING, progress=50) is False
    assert queue.complete(zombie.id, zombie.lease_token) is False
    assert queue.heartbeat(zombie.id, zombie.lease_token, lease_seconds=60) is None

    job = _get(owner.id)
    assert job.status == ResearchJobStatus.RUNNING
    assert job.lease_token == owner.lease_token
    assert job.progress == 0


def test_heartbeat_extends_lease_and_reports_cancel(make_job):
    make_job()
    claimed = queue.claim_next(lease_seconds=5)
    before = _get(claimed.id).lease_expires_at

    assert queue.heartbeat(claimed.id, claimed.lease_token, lease_seconds=600) is False
    assert _get(claimed.id).lease_expires_at > before

    with SessionLocal() as session:
        session.execute(text("UPDATE research_jobs SET cancel_requested = true WHERE id = :id"), {"id": claimed.id})
        session.commit()
    assert queue.heartbeat(claimed.id, claimed.lease_token, lease_seconds=600) is True


def test_progress_never_goes_backwards(make_job):
    make_job()
    claimed = queue.claim_next(lease_seconds=60)

    queue.set_stage(claimed.id, claimed.lease_token, stage=ResearchStage.ANALYZING, progress=60)
    queue.set_stage(claimed.id, claimed.lease_token, stage=ResearchStage.VERIFYING, progress=40)

    job = _get(claimed.id)
    assert job.progress == 60
    assert job.current_stage == ResearchStage.VERIFYING


def test_complete_sets_terminal_fields(make_job):
    make_job()
    claimed = queue.claim_next(lease_seconds=60)

    assert queue.complete(claimed.id, claimed.lease_token) is True

    job = _get(claimed.id)
    assert job.status == ResearchJobStatus.COMPLETED
    assert job.progress == 100
    assert job.completed_at is not None
    assert job.lease_token is None


def test_schedule_retry_requeues_with_delay_and_reason(make_job):
    make_job()
    claimed = queue.claim_next(lease_seconds=60)

    assert queue.schedule_retry(claimed.id, claimed.lease_token, error_message="SEC timed out", delay_seconds=300)

    job = _get(claimed.id)
    assert job.status == ResearchJobStatus.QUEUED
    assert job.error_message == "SEC timed out"
    assert job.run_after > job.updated_at
    assert queue.claim_next(lease_seconds=60) is None  # not before run_after


def test_fail_records_reason(make_job):
    make_job()
    claimed = queue.claim_next(lease_seconds=60)

    queue.fail(claimed.id, claimed.lease_token, error_message="Ticker ZZZZ not found on SEC EDGAR")

    job = _get(claimed.id)
    assert job.status == ResearchJobStatus.FAILED
    assert job.error_message == "Ticker ZZZZ not found on SEC EDGAR"
    assert job.completed_at is not None


def test_reaper_fails_expired_job_without_attempts_left(make_job):
    make_job(max_attempts=1)
    claimed = queue.claim_next(lease_seconds=60)
    _expire_lease(claimed.id)

    assert queue.claim_next(lease_seconds=60) is None
    assert queue.reap_exhausted() == [claimed.id]

    job = _get(claimed.id)
    assert job.status == ResearchJobStatus.FAILED
    assert "stopped responding" in job.error_message


def test_release_returns_job_without_spending_attempt(make_job):
    make_job()
    claimed = queue.claim_next(lease_seconds=60)

    assert queue.release(claimed.id, claimed.lease_token)

    job = _get(claimed.id)
    assert job.status == ResearchJobStatus.QUEUED
    assert job.attempts == 0
