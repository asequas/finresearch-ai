"""Provider failures inside the agent's tool loops map onto the job queue's error types."""
import pytest
from langchain_core.exceptions import ModelAuthenticationError, ModelRateLimitError

from backend.llm.chat import GeminiGuard, provider_error
from backend.pipeline.base import LeaseLost, PermanentError, ProviderBusyError, RetryableError


class _Coded(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ModelRateLimitError("slow down"), ProviderBusyError),
        (_Coded(429), ProviderBusyError),
        (_Coded(503), ProviderBusyError),
        (ModelAuthenticationError("bad key"), PermanentError),
        (_Coded(403), PermanentError),
        (TimeoutError("read timed out"), RetryableError),
    ],
)
def test_provider_errors_are_classified(exc, expected):
    assert type(provider_error(exc)) is expected


def test_job_errors_pass_through_unchanged():
    lost = LeaseLost("gone")
    assert provider_error(lost) is lost


def test_guard_maps_what_the_fallback_chain_gave_up_on():
    def handler(_request):
        raise _Coded(503)

    with pytest.raises(ProviderBusyError):
        GeminiGuard().wrap_model_call(object(), handler)
