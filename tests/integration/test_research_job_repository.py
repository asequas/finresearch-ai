import uuid

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models.research_job import ResearchJob, ResearchJobStatus
from backend.models.user import User
from backend.repositories.research_job import ResearchJobRepository


def test_create_research_job():
    email = f"repo-test-{uuid.uuid4()}@example.com"

    repository = ResearchJobRepository()

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        job = repository.create(
            session,
            user_id=user.id,
            query="Should I invest in Apple?",
            company="Apple Inc.",
            ticker="AAPL",
        )

        assert job.id is not None
        assert job.user_id == user.id
        assert job.query == "Should I invest in Apple?"
        assert job.company == "Apple Inc."
        assert job.ticker == "AAPL"
        assert job.status.value == "queued"

        session.commit()

        job_id = job.id

    # Verify persistence using a completely fresh session.
    with SessionLocal() as session:
        saved_job = session.scalar(
            select(ResearchJob).where(ResearchJob.id == job_id)
        )

        assert saved_job is not None
        assert saved_job.user_id == user.id
        assert saved_job.status.value == "queued"

def test_get_research_job_by_id():
    email = f"repo-get-test-{uuid.uuid4()}@example.com"

    repository = ResearchJobRepository()

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        created_job = repository.create(
            session,
            user_id=user.id,
            query="Analyze Microsoft",
            company="Microsoft Corporation",
            ticker="MSFT",
        )

        session.commit()

        job_id = created_job.id

    with SessionLocal() as session:
        saved_job = repository.get_by_id(
            session,
            job_id=job_id,
        )

        assert saved_job is not None
        assert saved_job.id == job_id
        assert saved_job.ticker == "MSFT"

        missing_job = repository.get_by_id(
            session,
            job_id=uuid.uuid4(),
        )

        assert missing_job is None

def test_update_research_job_status():
    email = f"repo-status-test-{uuid.uuid4()}@example.com"

    repository = ResearchJobRepository()

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        job = repository.create(
            session,
            user_id=user.id,
            query="Analyze Nvidia",
            company="NVIDIA Corporation",
            ticker="NVDA",
        )

        session.commit()
        job_id = job.id

    # Update the status.
    with SessionLocal() as session:
        updated_job = repository.update_status(
            session,
            job_id=job_id,
            status=ResearchJobStatus.RUNNING,
        )

        assert updated_job is not None
        assert updated_job.status == ResearchJobStatus.RUNNING

        session.commit()

    # Verify persistence using a fresh session.
    with SessionLocal() as session:
        saved_job = repository.get_by_id(
            session,
            job_id=job_id,
        )

        assert saved_job is not None
        assert saved_job.status == ResearchJobStatus.RUNNING

        missing_job = repository.update_status(
            session,
            job_id=uuid.uuid4(),
            status=ResearchJobStatus.FAILED,
        )

        assert missing_job is None

def test_update_research_job_progress():
    email = f"repo-progress-test-{uuid.uuid4()}@example.com"

    repository = ResearchJobRepository()

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        job = repository.create(
            session,
            user_id=user.id,
            query="Analyze Tesla",
            company="Tesla Inc.",
            ticker="TSLA",
        )

        session.commit()
        job_id = job.id

    # Test a normal progress update.
    with SessionLocal() as session:
        updated_job = repository.update_progress(
            session,
            job_id=job_id,
            progress=50,
        )

        assert updated_job is not None
        assert updated_job.progress == 50

        session.commit()

    # Verify persistence using a fresh session.
    with SessionLocal() as session:
        saved_job = repository.get_by_id(
            session,
            job_id=job_id,
        )

        assert saved_job is not None
        assert saved_job.progress == 50

    # Test valid boundary values.
    with SessionLocal() as session:
        assert repository.update_progress(
            session,
            job_id=job_id,
            progress=0,
        ).progress == 0

        assert repository.update_progress(
            session,
            job_id=job_id,
            progress=100,
        ).progress == 100

        session.rollback()

    # Test invalid values.
    with SessionLocal() as session:
        for invalid_progress in (-1, 101):
            try:
                repository.update_progress(
                    session,
                    job_id=job_id,
                    progress=invalid_progress,
                )
                assert False, f"Expected ValueError for {invalid_progress}"
            except ValueError:
                pass

    # Missing job should return None.
    with SessionLocal() as session:
        missing_job = repository.update_progress(
            session,
            job_id=uuid.uuid4(),
            progress=50,
        )

        assert missing_job is None