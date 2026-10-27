from sqlalchemy import func, select, text

from backend.core.database import SessionLocal, engine
from backend.models.user import User


def test_tests_run_against_test_database():
    with engine.connect() as connection:
        assert connection.execute(text("select current_database()")).scalar().endswith("_test")


def test_tables_start_empty_for_each_test():
    with SessionLocal() as session:
        session.add(User(email="leftover@example.com"))
        session.commit()


def test_previous_test_rows_were_truncated():
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0
