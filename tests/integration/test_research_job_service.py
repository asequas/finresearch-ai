import uuid

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models.research_job import ResearchJob, ResearchJobStatus
from backend.models.user import User
from backend.repositories.research_job import ResearchJobRepository
from backend.schemas.research import ResearchCreateRequest
from backend.services.research_job import ResearchJobService


def test_create_research_job_service():
    email = f"service-test-{uuid.uuid4()}@example.com"

    service = ResearchJobService(
        repository=ResearchJobRepository()
    )

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        request = ResearchCreateRequest(
            query="Should I invest in Apple?",
            company="Apple Inc.",
            ticker="AAPL",
        )

        job = service.create_research_job(
            session,
            user_id=user.id,
            request=request,
        )

        assert job.id is not None
        assert job.user_id == user.id
        assert job.query == request.query
        assert job.company == request.company
        assert job.ticker == request.ticker
        assert job.status == ResearchJobStatus.QUEUED

        session.commit()

        job_id = job.id

    # Verify persistence through a fresh session.
    with SessionLocal() as session:
        saved_job = session.scalar(
            select(ResearchJob).where(
                ResearchJob.id == job_id
            )
        )

        assert saved_job is not None
        assert saved_job.ticker == "AAPL"
        assert saved_job.status == ResearchJobStatus.QUEUED

def test_get_research_job_service():
    email = f"service-get-test-{uuid.uuid4()}@example.com"

    service = ResearchJobService(
        repository=ResearchJobRepository()
    )

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        request = ResearchCreateRequest(
            query="Analyze Microsoft",
            company="Microsoft Corporation",
            ticker="MSFT",
        )

        created_job = service.create_research_job(
            session,
            user_id=user.id,
            request=request,
        )

        session.commit()

        job_id = created_job.id

    with SessionLocal() as session:
        saved_job = service.get_research_job(
            session,
            job_id=job_id,
        )

        assert saved_job is not None
        assert saved_job.id == job_id
        assert saved_job.ticker == "MSFT"

        missing_job = service.get_research_job(
            session,
            job_id=uuid.uuid4(),
        )

        assert missing_job is None

def test_update_research_job_status_service():
    email = f"service-status-test-{uuid.uuid4()}@example.com"

    service = ResearchJobService(
        repository=ResearchJobRepository()
    )

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        request = ResearchCreateRequest(
            query="Analyze Nvidia",
            company="NVIDIA Corporation",
            ticker="NVDA",
        )

        job = service.create_research_job(
            session,
            user_id=user.id,
            request=request,
        )

        session.commit()
        job_id = job.id

    # queued → running is allowed.
    with SessionLocal() as session:
        updated_job = service.update_status(
            session,
            job_id=job_id,
            new_status=ResearchJobStatus.RUNNING,
        )

        assert updated_job is not None
        assert updated_job.status == ResearchJobStatus.RUNNING

        session.commit()

    # running → completed is allowed.
    with SessionLocal() as session:
        updated_job = service.update_status(
            session,
            job_id=job_id,
            new_status=ResearchJobStatus.COMPLETED,
        )

        assert updated_job is not None
        assert updated_job.status == ResearchJobStatus.COMPLETED

        session.commit()

    # completed → running is NOT allowed.
    with SessionLocal() as session:
        try:
            service.update_status(
                session,
                job_id=job_id,
                new_status=ResearchJobStatus.RUNNING,
            )
            assert False, "Expected ValueError for invalid transition"
        except ValueError as exc:
            assert "Invalid status transition" in str(exc)

    # Missing job should return None.
    with SessionLocal() as session:
        missing_job = service.update_status(
            session,
            job_id=uuid.uuid4(),
            new_status=ResearchJobStatus.RUNNING,
        )

        assert missing_job is None

def test_update_research_job_status_to_failed():
    email = f"service-failed-test-{uuid.uuid4()}@example.com"

    service = ResearchJobService(
        repository=ResearchJobRepository()
    )

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        request = ResearchCreateRequest(
            query="Analyze Tesla",
            company="Tesla Inc.",
            ticker="TSLA",
        )

        job = service.create_research_job(
            session,
            user_id=user.id,
            request=request,
        )

        session.commit()
        job_id = job.id

    # queued → running
    with SessionLocal() as session:
        updated_job = service.update_status(
            session,
            job_id=job_id,
            new_status=ResearchJobStatus.RUNNING,
        )

        assert updated_job is not None
        assert updated_job.status == ResearchJobStatus.RUNNING

        session.commit()

    # running → failed
    with SessionLocal() as session:
        updated_job = service.update_status(
            session,
            job_id=job_id,
            new_status=ResearchJobStatus.FAILED,
        )

        assert updated_job is not None
        assert updated_job.status == ResearchJobStatus.FAILED

        session.commit()

    # Verify persistence through a fresh session.
    with SessionLocal() as session:
        saved_job = service.get_research_job(
            session,
            job_id=job_id,
        )

        assert saved_job is not None
        assert saved_job.status == ResearchJobStatus.FAILED

def test_update_research_job_progress_service():
    email = f"service-progress-test-{uuid.uuid4()}@example.com"

    service = ResearchJobService(
        repository=ResearchJobRepository()
    )

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        request = ResearchCreateRequest(
            query="Analyze Amazon",
            company="Amazon.com, Inc.",
            ticker="AMZN",
        )

        job = service.create_research_job(
            session,
            user_id=user.id,
            request=request,
        )

        session.commit()
        job_id = job.id

    # Test a normal progress update.
    with SessionLocal() as session:
        updated_job = service.update_progress(
            session,
            job_id=job_id,
            progress=50,
        )

        assert updated_job is not None
        assert updated_job.progress == 50

        session.commit()

    # Verify persistence through a fresh session.
    with SessionLocal() as session:
        saved_job = service.get_research_job(
            session,
            job_id=job_id,
        )

        assert saved_job is not None
        assert saved_job.progress == 50

    # Valid boundaries.
    with SessionLocal() as session:
        updated_job = service.update_progress(
            session,
            job_id=job_id,
            progress=0,
        )
        assert updated_job is not None
        assert updated_job.progress == 0

        updated_job = service.update_progress(
            session,
            job_id=job_id,
            progress=100,
        )
        assert updated_job is not None
        assert updated_job.progress == 100

        session.rollback()

    # Invalid values.
    with SessionLocal() as session:
        for invalid_progress in (-1, 101):
            try:
                service.update_progress(
                    session,
                    job_id=job_id,
                    progress=invalid_progress,
                )
                assert False, (
                    f"Expected ValueError for progress={invalid_progress}"
                )
            except ValueError as exc:
                assert "progress must be between 0 and 100" in str(exc)

    # Missing job.
    with SessionLocal() as session:
        missing_job = service.update_progress(
            session,
            job_id=uuid.uuid4(),
            progress=50,
        )

        assert missing_job is None