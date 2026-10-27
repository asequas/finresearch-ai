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


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
