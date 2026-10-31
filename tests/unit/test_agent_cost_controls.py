"""Token and request controls for the agent's tool loops (ADR 0009)."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from backend.agent.context import MARKER, compact_messages
from backend.llm.chat import ModelCoolingDown, _paced_class
from backend.llm.pacing import COOLDOWN

PASSAGE = "[P:1a2b3c4d] 10-K for period ending 2024-09-30 · mdna\n" + "Net sales grew because of strong demand. " * 40


def _tool(i, content=PASSAGE, name="search_filings"):
    return ToolMessage(content=content, tool_call_id=f"c{i}", name=name)


def test_old_search_results_shrink_to_citable_handles_and_the_latest_stay_whole():
    messages = [HumanMessage("q"), _tool(1), AIMessage(""), _tool(2), AIMessage(""), _tool(3), _tool(4, "M1: Operating margin", "get_metrics")]

    out = compact_messages(messages, keep=2)

    assert out[1].content.startswith(MARKER) and "[P:1a2b3c4d] 10-K for period ending 2024-09-30 · mdna" in out[1].content
    assert len(out[1].content) < 300 < len(PASSAGE)
    assert out[3].content == PASSAGE and out[5].content == PASSAGE  # the two latest search results
    assert out[6].content == "M1: Operating margin"  # small tools are never touched
    assert messages[1].content == PASSAGE  # the agent's own state is unchanged
    assert compact_messages(out, keep=2)[1].content == out[1].content  # idempotent


@pytest.fixture
def paced(monkeypatch):
    from langchain_google_genai import ChatGoogleGenerativeAI

    recorded = []
    monkeypatch.setattr("backend.llm.chat.record_call", lambda **kw: recorded.append(kw))
    monkeypatch.setattr("backend.llm.chat.ensure_budget", lambda: None)
    model = _paced_class()(model="gemini-3.5-flash-lite", google_api_key="test", max_retries=0)
    return model, recorded, ChatGoogleGenerativeAI


def test_paced_model_records_tokens_including_thinking_and_cache(paced, monkeypatch):
    model, recorded, base = paced
    message = AIMessage("ok", usage_metadata={
        "input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500,
        "input_token_details": {"cache_read": 400}, "output_token_details": {"reasoning": 100},
    })
    monkeypatch.setattr(base, "_generate", lambda self, *a, **k: ChatResult(generations=[ChatGeneration(message=message)]))

    model.invoke("hi")

    assert recorded == [dict(model="gemini-3.5-flash-lite", operation="generate", input_tokens=1200, cached_tokens=400,
                             output_tokens=300, thinking_tokens=100, estimated=False)]


def test_a_429_puts_the_model_in_cooldown_and_the_next_call_fails_fast(paced, monkeypatch):
    model, recorded, base = paced
    calls = []

    class RateLimited(Exception):
        code = 429

    def rate_limited(self, *a, **k):
        calls.append(1)
        raise RateLimited("retryDelay: '30s'")

    monkeypatch.setattr(base, "_generate", rate_limited)

    with pytest.raises(Exception):
        model.invoke("hi")
    with pytest.raises(ModelCoolingDown):
        model.invoke("hi")
    assert calls == [1]  # no second network call
    assert 25 < COOLDOWN.remaining("gemini-3.5-flash-lite") <= 30
