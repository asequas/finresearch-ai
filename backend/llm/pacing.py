"""Per-model request pacing and cool-downs, shared by every Gemini client in the process (ADR 0009).

A 429 from one model means "this model, for a while", not "everything now": the model is skipped for the delay
Google suggests, so the next call goes straight to a model that can answer instead of spending a round trip on
a guaranteed rejection.
"""
import threading
import time
from collections import deque

from backend.core.config import settings

DEFAULT_COOLDOWN_SECONDS = 60.0
OVERLOAD_COOLDOWN_SECONDS = 20.0


class ModelCooldown:
    def __init__(self):
        self.lock = threading.Lock()
        self.until: dict[str, float] = {}

    def remaining(self, model: str) -> float:
        with self.lock:
            return max(0.0, self.until.get(model, 0.0) - time.monotonic())

    def cool(self, model: str, seconds: float) -> None:
        with self.lock:
            self.until[model] = max(self.until.get(model, 0.0), time.monotonic() + seconds)

    def reset(self) -> None:
        with self.lock:
            self.until.clear()


class ModelPacer:
    """At most `gemini_model_rpm[model]` requests per rolling minute per model (unset = unlimited)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls: dict[str, deque[float]] = {}

    def acquire(self, model: str) -> None:
        limit = settings.gemini_model_rpm.get(model)
        if not limit:
            return
        while True:
            with self.lock:
                now = time.monotonic()
                window = self.calls.setdefault(model, deque())
                while window and now - window[0] >= 60:
                    window.popleft()
                if len(window) < limit:
                    window.append(now)
                    return
                wait = 60 - (now - window[0]) + 0.05
            time.sleep(wait)


COOLDOWN = ModelCooldown()
PACER = ModelPacer()
