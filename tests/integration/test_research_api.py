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