from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_create_research_job_api():
    response = client.post(
        "/api/v1/research",
        json={
            "query": "Should I invest in Apple?",
            "company": "Apple Inc.",
            "ticker": "AAPL",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["query"] == "Should I invest in Apple?"
    assert data["company"] == "Apple Inc."
    assert data["ticker"] == "AAPL"
    assert data["status"] == "queued"
    assert data["current_stage"] is None
    assert data["progress"] == 0

def test_create_research_job_api_validation():
    response = client.post(
        "/api/v1/research",
        json={
            "query": "",
            "company": "Apple Inc.",
            "ticker": "AAPL",
        },
    )

    assert response.status_code == 422

def test_get_research_job_api():
    # Create a job first.
    create_response = client.post(
        "/api/v1/research",
        json={
            "query": "Should I invest in Apple?",
            "company": "Apple Inc.",
            "ticker": "AAPL",
        },
    )

    assert create_response.status_code == 201

    created_job = create_response.json()
    job_id = created_job["id"]

    # Fetch the job.
    response = client.get(
        f"/api/v1/research/{job_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == job_id
    assert data["query"] == "Should I invest in Apple?"
    assert data["company"] == "Apple Inc."
    assert data["ticker"] == "AAPL"
    assert data["status"] == "queued"
    assert data["progress"] == 0


def test_get_research_job_api_not_found():
    response = client.get(
        "/api/v1/research/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Research job not found"