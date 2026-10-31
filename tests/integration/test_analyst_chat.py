"""'Ask the analyst': a tool-using follow-up agent whose citations are verified before they're stored."""
import pytest
from fastapi.testclient import TestClient

from backend.analysis.rerank import NoopReranker
from backend.api.routes.research import get_chat_service
from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.main import app
from backend.pipeline.base import ProviderBusyError
from backend.pipeline.research import Services, research_stages
from backend.services.analyst_chat import AnalystChatService
from backend.services.user import UserService
from backend.worker.main import Worker
from tests.fakes import FakeLLM, FakeSec, ScriptedAnalyst, ScriptedResearcher, scripted_agent_model


@pytest.fixture
def finished_job(make_job, tmp_path):
    with SessionLocal() as session:
        user = UserService().get_or_create_dev_user(session)
    job = make_job(user=user, ticker="WDGT")
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM,
                        agent_model_factory=scripted_agent_model(ScriptedResearcher()))
    Worker(stages_factory=lambda: research_stages(services), retry_base_seconds=0).run_once()
    return job


@pytest.fixture
def client():
    def use(model):
        app.dependency_overrides[get_chat_service] = lambda: AnalystChatService(
            agent_model_factory=scripted_agent_model(model), llm_factory=FakeLLM, reranker_factory=NoopReranker,
        )
    yield TestClient(app), use
    app.dependency_overrides.pop(get_chat_service, None)


def test_answer_is_stored_with_checked_citations_and_tool_steps(finished_job, client):
    http, use = client
    use(ScriptedAnalyst())

    empty = http.get(f"/api/v1/research/{finished_job.id}/chat").json()
    response = http.post(f"/api/v1/research/{finished_job.id}/chat", json={"question": "What could disrupt supply?"})

    assert empty["messages"] == [] and empty["suggestions"] == ["How concentrated are customers?"]
    assert response.status_code == 200, response.text
    body = response.json()
    question, answer = body["messages"]
    assert (question["role"], question["content"]) == ("user", "What could disrupt supply?")
    assert answer["role"] == "assistant" and answer["content"].startswith("Steel supply")
    good, bad = answer["citations"]
    assert good["verified"] is True and good["form"] == "10-K" and good["period"] == "2024-09-30"
    assert bad["verified"] is False  # the fabricated quote is stored, but flagged
    assert answer["tool_steps"][0]["tool"] == "search_filings"
    assert body["turns_left"] == settings.chat_max_turns - 1 and body["suggestions"] == []
    assert http.get(f"/api/v1/research/{finished_job.id}/chat").json()["messages"] == body["messages"]


def test_turn_limit_returns_429(finished_job, client, monkeypatch):
    http, use = client
    use(ScriptedAnalyst())
    monkeypatch.setattr(settings, "chat_max_turns", 1)

    assert http.post(f"/api/v1/research/{finished_job.id}/chat", json={"question": "First question?"}).status_code == 200
    limited = http.post(f"/api/v1/research/{finished_job.id}/chat", json={"question": "Second question?"})

    assert limited.status_code == 429


def test_busy_provider_returns_503_and_stores_nothing(finished_job, client):
    http, use = client
    use(ScriptedAnalyst(fail_once="supply"))

    response = http.post(f"/api/v1/research/{finished_job.id}/chat", json={"question": "What could disrupt supply?"})

    assert response.status_code == 503 and response.headers["retry-after"] == "60"
    assert http.get(f"/api/v1/research/{finished_job.id}/chat").json()["messages"] == []


def test_no_report_means_404(make_job, client):
    http, use = client
    use(ScriptedAnalyst())
    with SessionLocal() as session:
        user = UserService().get_or_create_dev_user(session)
    job = make_job(user=user)

    assert http.get(f"/api/v1/research/{job.id}/chat").status_code == 404
    assert http.post(f"/api/v1/research/{job.id}/chat", json={"question": "Anything?"}).status_code == 404
    assert http.post(f"/api/v1/research/{job.id}/chat", json={"question": "x"}).status_code == 422
