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
# Tests never reach Gemini: no key, free-tier accounting, and every SDK request path is blocked below.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_BILLING"] = "free"
# Tests never download models; the cross-encoder has its own opt-in test (pytest -m model).
os.environ.setdefault("RERANKER", "none")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend.core.database import engine  # noqa: E402
from backend.models import Base  # noqa: E402


class GeminiCallBlocked(RuntimeError):
    pass


@pytest.fixture(scope="session", autouse=True)
def no_gemini_calls():
    """Fail loudly if any test tries to reach the Gemini API: the project's key is billed.

    Covers the google-genai SDK's sync and async request methods, which both GeminiClient and
    langchain-google-genai go through. Tests use FakeLLM / ScriptedResearcher instead.
    """
    from google.genai import models

    def blocked(*_args, **_kwargs):
        raise GeminiCallBlocked("A test tried to call the Gemini API. Use the fakes in tests/fakes.py.")

    patched = []
    for cls in (models.Models, models.AsyncModels):
        for name in ("generate_content", "generate_content_stream", "embed_content", "count_tokens"):
            if hasattr(cls, name):
                patched.append((cls, name, getattr(cls, name)))
                setattr(cls, name, blocked)
    yield
    for cls, name, original in patched:
        setattr(cls, name, original)


@pytest.fixture(scope="session", autouse=True)
def fixed_risk_free_rate():
    """The DCF's risk-free rate is pinned in tests: no treasury.gov calls, no dependence on the dev cache."""
    from datetime import date
    from decimal import Decimal

    from backend.valuation import market

    original = market.latest_risk_free_rate
    market.latest_risk_free_rate = lambda *args, **kwargs: market.RiskFreeRate(
        Decimal("0.0450"), date(2026, 10, 30), market.TREASURY_PAGE
    )
    yield
    market.latest_risk_free_rate = original


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


@pytest.fixture(autouse=True)
def fresh_model_cooldowns():
    """Model cool-downs are process-wide state; a 429 in one test must not skip models in the next."""
    from backend.llm.pacing import COOLDOWN

    COOLDOWN.reset()
    yield
    COOLDOWN.reset()
