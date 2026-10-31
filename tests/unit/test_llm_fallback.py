from types import SimpleNamespace

import pytest
from google.genai import errors
from pydantic import BaseModel

from backend.llm.client import GeminiClient
from backend.pipeline.base import RetryableError


class Out(BaseModel):
    answer: str


def _client(responses: dict):
    """A GeminiClient whose transport answers per model: an int is an HTTP error code."""
    calls: list[str] = []

    def generate_content(*, model, contents, config):
        calls.append(model)
        outcome = responses[model]
        if isinstance(outcome, int):
            raise errors.APIError(outcome, {"error": {"code": outcome, "message": "busy", "status": "UNAVAILABLE"}})
        return SimpleNamespace(text=outcome, usage_metadata=None)

    client = GeminiClient.__new__(GeminiClient)
    client.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    client.strong_model, client.fast_model = "strong-a", "fast-a"
    client.strong_fallbacks, client.fast_fallbacks = ["strong-b", "strong-c"], []
    client.throttle = SimpleNamespace(wait=lambda: None)
    return client, calls


def test_overloaded_model_falls_back_to_the_next_one():
    client, calls = _client({"strong-a": 503, "strong-b": 429, "strong-c": '{"answer": "ok"}'})

    result = client.generate_json(prompt="p", schema=Out, system="s", strong=True)

    assert calls == ["strong-a", "strong-b", "strong-c"]
    assert result.model == "strong-c"
    assert result.value.answer == "ok"


def test_bad_request_does_not_fall_back():
    client, calls = _client({"strong-a": 400, "strong-b": '{"answer": "ok"}'})

    with pytest.raises(RetryableError):
        client.generate_json(prompt="p", schema=Out, system="s", strong=True)
    assert calls == ["strong-a"]


def test_all_models_down_is_retryable():
    client, _ = _client({"strong-a": 503, "strong-b": 503, "strong-c": 503})

    with pytest.raises(RetryableError):
        client.generate_json(prompt="p", schema=Out, system="s", strong=True)


def test_a_rate_limited_model_is_skipped_until_its_cooldown_ends():
    client, calls = _client({"strong-a": 429, "strong-b": '{"answer": "ok"}', "strong-c": '{"answer": "ok"}'})

    client.generate_json(prompt="p", schema=Out, system="s", strong=True)
    client.generate_json(prompt="p", schema=Out, system="s", strong=True)

    # The second call goes straight to strong-b instead of spending a round trip on a guaranteed 429.
    assert calls == ["strong-a", "strong-b", "strong-b"]


def test_when_every_model_is_cooling_the_soonest_is_tried():
    from backend.llm.pacing import COOLDOWN

    client, calls = _client({"strong-a": '{"answer": "ok"}', "strong-b": 503, "strong-c": 503})
    COOLDOWN.cool("strong-a", 30)
    COOLDOWN.cool("strong-b", 60)
    COOLDOWN.cool("strong-c", 90)

    client.generate_json(prompt="p", schema=Out, system="s", strong=True)

    assert calls == ["strong-a"]
