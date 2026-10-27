"""Test harness: every test runs against an isolated `*_test` database.

DATABASE_URL is overridden before any `backend` module is imported, because
settings and the engine are created at import time.
"""
import os

from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://finresearch:finresearch_dev@localhost:5432/finresearch_test",
)

if not make_url(TEST_DATABASE_URL).database.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against {make_url(TEST_DATABASE_URL).database!r}: "
        "the test database name must end with '_test'."
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend.core.database import engine  # noqa: E402
from backend.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture
def make_user():
    from backend.core.database import SessionLocal
    from backend.models.user import User

    def _make(email: str | None = None) -> User:
        import uuid

        with SessionLocal() as session:
            user = User(email=email or f"user-{uuid.uuid4()}@example.com")
            session.add(user)
            session.commit()
            return user

    return _make


@pytest.fixture
def make_job(make_user):
    from backend.core.database import SessionLocal
    from backend.repositories.research_job import ResearchJobRepository
    from backend.schemas.research import ResearchCreateRequest
    from backend.services.research_job import ResearchJobService

    def _make(user=None, ticker: str = "AAPL", max_attempts: int = 3, **overrides):
        user = user or make_user()
        with SessionLocal() as session:
            job = ResearchJobService(ResearchJobRepository()).submit(
                session,
                user_id=user.id,
                request=ResearchCreateRequest(query="Is Apple financially strong?", company="Apple Inc.", ticker=ticker),
            )
            job.max_attempts = max_attempts
            for key, value in overrides.items():
                setattr(job, key, value)
            session.commit()
            return job

    return _make


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
