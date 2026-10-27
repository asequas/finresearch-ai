import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.core.database import SessionLocal
from backend.main import app
from backend.models.research_job import ResearchJob, ResearchJobStatus
from backend.models.user import User
from backend.services.user import DEV_USER_EMAIL


client = TestClient(app)

PAYLOAD = {
    "query": "Should I invest in Apple?",
    "company": "Apple Inc.",
    "ticker": "AAPL",
}


def test_create_research_job_returns_202_with_location():
    response = client.post("/api/v1/research", json=PAYLOAD)

    assert response.status_code == 202

    data = response.json()
    assert response.headers["Location"] == f"/api/v1/research/{data['id']}"
    assert data["status"] == "queued"
    assert data["current_stage"] is None
    assert data["progress"] == 0
    assert data["attempts"] == 0
    assert data["created_at"] is not None
    assert data["error_message"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 2001},
        {"company": "  "},
        {"ticker": ""},
        {"ticker": "NOT A TICKER"},
        {"ticker": "1ABC"},
    ],
)
def test_create_research_job_validation(overrides):
    response = client.post("/api/v1/research", json={**PAYLOAD, **overrides})

    assert response.status_code == 422


def test_create_research_job_normalises_input():
    response = client.post(
        "/api/v1/research",
        json={"query": "  Is it strong?  ", "company": " Apple Inc. ", "ticker": " brk.b "},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["query"] == "Is it strong?"
    assert data["company"] == "Apple Inc."
    assert data["ticker"] == "BRK.B"


def test_get_research_job_api():
    job_id = client.post("/api/v1/research", json=PAYLOAD).json()["id"]

    response = client.get(f"/api/v1/research/{job_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["stages"] == []
    assert data["has_report"] is False


def test_get_research_job_api_not_found():
    response = client.get("/api/v1/research/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "Research job not found"


def test_get_another_users_job_returns_404(make_job):
    other_users_job = make_job()

    response = client.get(f"/api/v1/research/{other_users_job.id}")

    assert response.status_code == 404


def test_idempotency_key_returns_same_job():
    headers = {"Idempotency-Key": "submit-form-1"}

    first = client.post("/api/v1/research", json=PAYLOAD, headers=headers)
    second = client.post("/api/v1/research", json=PAYLOAD, headers=headers)

    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    with SessionLocal() as session:
        assert session.query(ResearchJob).count() == 1


def test_idempotency_key_with_different_payload_conflicts():
    headers = {"Idempotency-Key": "submit-form-2"}
    client.post("/api/v1/research", json=PAYLOAD, headers=headers)

    response = client.post("/api/v1/research", json={**PAYLOAD, "ticker": "MSFT"}, headers=headers)

    assert response.status_code == 409


def test_concurrent_requests_with_same_key_create_one_job():
    client.get("/health")
    client.post("/api/v1/research", json=PAYLOAD)  # make sure the dev user exists
    ids, barrier = [], threading.Barrier(8)

    def submit():
        barrier.wait()
        ids.append(client.post("/api/v1/research", json=PAYLOAD, headers={"Idempotency-Key": "race"}).json()["id"])

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(ids)) == 1


def test_concurrent_first_requests_create_one_dev_user():
    barrier = threading.Barrier(8)
    codes = []

    def submit():
        barrier.wait()
        codes.append(client.post("/api/v1/research", json=PAYLOAD).status_code)

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert codes == [202] * 8
    with SessionLocal() as session:
        assert session.query(User).filter(User.email == DEV_USER_EMAIL).count() == 1


def test_list_research_jobs_paginates_newest_first():
    ids = [client.post("/api/v1/research", json={**PAYLOAD, "query": f"q{i}"}).json()["id"] for i in range(5)]

    first = client.get("/api/v1/research", params={"limit": 2}).json()
    second = client.get("/api/v1/research", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    third = client.get("/api/v1/research", params={"limit": 2, "cursor": second["next_cursor"]}).json()

    seen = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert seen == list(reversed(ids))
    assert third["next_cursor"] is None


def test_list_filters_by_status_and_ticker():
    client.post("/api/v1/research", json=PAYLOAD)
    client.post("/api/v1/research", json={**PAYLOAD, "ticker": "MSFT", "company": "Microsoft"})

    by_ticker = client.get("/api/v1/research", params={"ticker": "msft"}).json()["items"]
    completed = client.get("/api/v1/research", params={"status": "completed"}).json()["items"]

    assert [item["ticker"] for item in by_ticker] == ["MSFT"]
    assert completed == []


def test_list_rejects_bad_cursor():
    assert client.get("/api/v1/research", params={"cursor": "garbage"}).status_code == 400


def test_list_excludes_other_users_jobs(make_job):
    make_job()

    assert client.get("/api/v1/research").json()["items"] == []


def test_cancel_queued_job():
    job_id = client.post("/api/v1/research", json=PAYLOAD).json()["id"]

    response = client.post(f"/api/v1/research/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["completed_at"] is not None
    assert client.post(f"/api/v1/research/{job_id}/cancel").status_code == 409


def test_retry_cancelled_job_requeues_it():
    job_id = client.post("/api/v1/research", json=PAYLOAD).json()["id"]
    client.post(f"/api/v1/research/{job_id}/cancel")

    response = client.post(f"/api/v1/research/{job_id}/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["completed_at"] is None


def test_retry_queued_job_conflicts():
    job_id = client.post("/api/v1/research", json=PAYLOAD).json()["id"]

    assert client.post(f"/api/v1/research/{job_id}/retry").status_code == 409


def test_cancel_running_job_sets_flag():
    job_id = client.post("/api/v1/research", json=PAYLOAD).json()["id"]
    with SessionLocal() as session:
        job = session.get(ResearchJob, uuid.UUID(job_id))
        job.status = ResearchJobStatus.RUNNING
        session.commit()

    response = client.post(f"/api/v1/research/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["cancel_requested"] is True


def test_meta_reports_configuration_and_queue_depth():
    client.post("/api/v1/research", json=PAYLOAD)

    body = client.get("/api/v1/meta").json()

    assert body["queue"]["queued"] == 1
    assert body["queue"]["running"] == 0
    assert body["queue"]["oldest_queued_seconds"] >= 0
    assert isinstance(body["gemini_configured"], bool)
    assert "embedding" in body["models"]
