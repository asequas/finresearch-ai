"""The test suite must never spend money on the Gemini API."""
import pytest
from google import genai

from backend.core.config import settings


def test_tests_run_without_a_gemini_key_and_on_free_tier_accounting():
    assert not settings.gemini_api_key
    assert settings.gemini_billing == "free"


def test_any_sdk_request_is_blocked_even_with_a_key():
    client = genai.Client(api_key="not-a-real-key")
    for call in (
        lambda: client.models.generate_content(model="gemini-3.5-flash-lite", contents="hi"),
        lambda: client.models.embed_content(model="gemini-embedding-001", contents=["hi"]),
        lambda: client.models.count_tokens(model="gemini-embedding-001", contents=["hi"]),
    ):
        with pytest.raises(RuntimeError, match="tried to call the Gemini API"):
            call()


def test_the_retrieval_eval_refuses_to_embed_without_live_flag(capsys):
    from backend.evals.retrieval import main

    assert main([]) == 2
    assert "--live" in capsys.readouterr().out
