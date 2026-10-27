import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.core.database import SessionLocal


@pytest.mark.parametrize(
    "assignment",
    [
        "status = 'banana'",
        "current_stage = 'not_a_stage'",
        "progress = 101",
        "progress = -1",
        "attempts = -1",
        "max_attempts = 0",
    ],
)
def test_database_rejects_invalid_job_state(make_job, assignment):
    job = make_job()

    with SessionLocal() as session, pytest.raises(IntegrityError):
        session.execute(text(f"UPDATE research_jobs SET {assignment} WHERE id = :id"), {"id": job.id})
        session.flush()


def test_raw_sql_insert_gets_server_defaults(make_user):
    user = make_user()

    with SessionLocal() as session:
        row = session.execute(
            text(
                "INSERT INTO research_jobs (id, user_id, query, company, ticker) "
                "VALUES (gen_random_uuid(), :user_id, 'q', 'c', 'T') "
                "RETURNING status, progress, attempts, created_at"
            ),
            {"user_id": user.id},
        ).one()
        session.commit()

    assert row.status == "queued"
    assert row.progress == 0
    assert row.attempts == 0
    assert row.created_at is not None
