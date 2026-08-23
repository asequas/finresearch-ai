import uuid

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models.user import User
from backend.models.research_job import ResearchJob


def test_user_and_research_job_persistence():
    email = f"test-{uuid.uuid4()}@example.com"

    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.flush()

        job = ResearchJob(
            user_id=user.id,
            query="Should I invest in Apple?",
            company="Apple Inc.",
            ticker="AAPL",
        )

        session.add(job)
        session.commit()

        job_id = job.id
        user_id = user.id

    # Read back using a fresh session
    with SessionLocal() as session:
        saved_job = session.scalar(
            select(ResearchJob).where(
                ResearchJob.id == job_id
            )
        )

        assert saved_job is not None
        assert saved_job.user_id == user_id
        assert saved_job.ticker == "AAPL"
        assert saved_job.status.value == "queued"

        saved_user = session.scalar(
            select(User).where(
                User.id == user_id
            )
        )

        assert saved_user is not None
        assert saved_user.email == email

        assert saved_job.user.id == user_id