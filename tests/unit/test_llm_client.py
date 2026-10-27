import time

from backend.llm.client import _WindowLimiter, normalise, retry_delay_seconds


def test_retry_delay_parsed_from_api_details():
    class QuotaError(Exception):
        details = {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "36s"}]}}

    assert retry_delay_seconds(QuotaError("quota")) == 36.0
    assert retry_delay_seconds(Exception("no hint")) == 30.0


def test_window_limiter_allows_up_to_the_limit_without_waiting():
    limiter = _WindowLimiter(limit=10)
    started = time.monotonic()
    limiter.acquire(6)
    limiter.acquire(4)
    assert time.monotonic() - started < 0.1
    assert sum(n for _, n in limiter.events) == 10


def test_normalise_gives_unit_vectors():
    vector = normalise([3.0, 4.0])
    assert vector == [0.6, 0.8]
