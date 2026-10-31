"""Provider-agnostic LLM adapter (ADR 0006): structured JSON generation + embeddings."""
import logging
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from backend.core.config import settings
from backend.costs.budget import ensure_budget
from backend.costs.ledger import record_call
from backend.llm.pacing import COOLDOWN, DEFAULT_COOLDOWN_SECONDS, OVERLOAD_COOLDOWN_SECONDS, PACER
from backend.models.document_chunk import EMBEDDING_DIMENSION
from backend.pipeline.base import PermanentError, ProviderBusyError, RetryableError

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


@dataclass
class LLMResult(Generic[T]):
    value: T
    model: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    fast_model: str
    strong_model: str

    def generate_json(
        self, *, prompt: str, schema: type[T], system: str, strong: bool = False, temperature: float = 0.2
    ) -> LLMResult[T]: ...

    def embed(self, texts: list[str], *, task: str) -> list[list[float]]: ...


def normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class _Throttle:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self) -> None:
        with self.lock:
            delay = self.last + self.min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()


class _WindowLimiter:
    """At most `limit` units per rolling 60 seconds, across threads."""

    def __init__(self, limit: int):
        self.limit = limit
        self.lock = threading.Lock()
        self.events: deque[tuple[float, int]] = deque()

    def acquire(self, units: int) -> None:
        units = min(units, self.limit)
        while True:
            with self.lock:
                now = time.monotonic()
                while self.events and now - self.events[0][0] >= 60:
                    self.events.popleft()
                used = sum(n for _, n in self.events)
                if used + units <= self.limit:
                    self.events.append((now, units))
                    return
                wait = 60 - (now - self.events[0][0]) + 0.05
            time.sleep(wait)


# One pacing budget per process, shared by the structured client and the agent's tool-calling models.
GEMINI_THROTTLE = _Throttle(min_interval=1.0)


def retry_delay_seconds(exc: Exception, default: float = 30.0) -> float:
    """The API's suggested wait (RetryInfo.retryDelay, e.g. '36s') when it gives one."""
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(getattr(exc, "details", "")) + str(exc))
    return float(match.group(1)) if match else default


class GeminiClient:
    """Gemini via google-genai. 429/5xx become RetryableError so the job queue backs off."""

    def __init__(self, api_key: str | None = None):
        from google import genai
        from google.genai import types

        key = api_key or settings.gemini_api_key
        if not key:
            raise PermanentError("GEMINI_API_KEY is not configured. Add it to .env to run research jobs.")
        # One SDK-level attempt with a hard timeout: retries belong to the job queue, where they are visible.
        self.client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                timeout=settings.gemini_timeout_seconds * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.fast_model = settings.gemini_fast_model
        self.strong_model = settings.gemini_strong_model
        self.strong_fallbacks = settings.gemini_strong_fallbacks
        self.fast_fallbacks = settings.gemini_fast_fallbacks
        self.embedding_model = settings.gemini_embedding_model
        self.throttle = GEMINI_THROTTLE
        self.embed_limiter = _WindowLimiter(settings.gemini_embed_per_minute)

    @staticmethod
    def _raise(exc) -> None:
        message = str(exc.message or "").split("For more information")[0].strip()
        if exc.code in (401, 403):
            raise PermanentError("The Gemini API key was rejected. Check GEMINI_API_KEY in .env.") from exc
        if exc.code == 429:
            raise ProviderBusyError(f"Gemini's free-tier quota is used up for now ({message}).") from exc
        if exc.code in (500, 502, 503, 504):
            raise ProviderBusyError(f"Gemini is overloaded (HTTP {exc.code}). This usually clears within minutes.") from exc
        raise RetryableError(f"Gemini API {exc.code}: {message}") from exc

    def generate_json(
        self, *, prompt: str, schema: type[T], system: str, strong: bool = False, temperature: float = 0.2
    ) -> LLMResult[T]:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
            # We never pass tools; AFC only adds a code path and a warning on every call.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        last_error: Exception | None = None
        for _ in range(2):  # one repair attempt for malformed output
            model, response = self._generate_with_fallback(strong, prompt, config)
            usage = response.usage_metadata
            _record_generation(model, usage)  # billed whether or not the output parses
            try:
                value = schema.model_validate_json(response.text or "")
            except ValidationError as exc:
                last_error = exc
                continue
            return LLMResult(
                value=value,
                model=model,
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0,
            )
        raise RetryableError(f"{model} returned output that did not match the schema: {last_error}")

    def _generate_with_fallback(self, strong: bool, prompt: str, config):
        """Try the preferred model, then same-tier fallbacks when it is overloaded or out of quota.

        Separate models have separate free-tier quotas, and a 503 "high demand" on one rarely
        means all are down. Anything else (bad request, auth) is not a reason to switch.
        """
        from google.genai import errors, types

        ensure_budget()
        preferred = self.strong_model if strong else self.fast_model
        full_chain = [preferred, *[m for m in (self.strong_fallbacks if strong else self.fast_fallbacks) if m != preferred]]
        # Skip models still cooling down from a 429; if all are, try the one that recovers first.
        chain = [m for m in full_chain if COOLDOWN.remaining(m) == 0] or [min(full_chain, key=COOLDOWN.remaining)]
        for index, model in enumerate(chain):
            PACER.acquire(model)
            self.throttle.wait()
            # Lite models may not accept a thinking level; reasoning models get a bounded one.
            call_config = config if "lite" in model else config.model_copy(
                update={"thinking_config": types.ThinkingConfig(thinking_level=settings.gemini_thinking_level)}
            )
            try:
                return model, self.client.models.generate_content(model=model, contents=prompt, config=call_config)
            except errors.APIError as exc:
                if exc.code == 429:
                    COOLDOWN.cool(model, retry_delay_seconds(exc, DEFAULT_COOLDOWN_SECONDS))
                elif exc.code in (500, 503, 504):
                    COOLDOWN.cool(model, OVERLOAD_COOLDOWN_SECONDS)
                if exc.code in (429, 500, 503, 504) and index < len(chain) - 1:
                    logger.warning("%s unavailable (%s); falling back to %s", model, exc.code, chain[index + 1])
                    continue
                self._raise(exc)
            except Exception as exc:  # network errors from the transport layer
                raise RetryableError(f"Gemini request failed: {type(exc).__name__}: {exc}") from exc
        raise RetryableError("No Gemini model was available")

    def embed(self, texts: list[str], *, task: str) -> list[list[float]]:
        from google.genai import errors, types

        task_type = "RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT"
        vectors: list[list[float]] = []
        batch_size = 30
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            for attempt in range(5):
                ensure_budget()
                self.embed_limiter.acquire(len(batch))
                try:
                    response = self.client.models.embed_content(
                        model=self.embedding_model,
                        contents=batch,
                        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMENSION),
                    )
                    break
                except errors.APIError as exc:
                    # A per-minute quota clears quickly: wait it out here instead of failing the whole stage.
                    if exc.code == 429 and attempt < 4:
                        time.sleep(min(retry_delay_seconds(exc), 65))
                        continue
                    self._raise(exc)
                except Exception as exc:
                    raise RetryableError(f"Gemini request failed: {type(exc).__name__}: {exc}") from exc
            self._record_embedding(batch)
            # Gemini only normalises full-size (3072-d) embeddings; truncated ones must be renormalised.
            vectors.extend(normalise(list(embedding.values)) for embedding in response.embeddings)
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMENSION for v in vectors):
            raise RetryableError("Embedding response had the wrong shape")
        return vectors


    def _record_embedding(self, batch: list[str]) -> None:
        """Embedding responses carry no token counts; count them with the (free) countTokens endpoint."""
        try:
            tokens, estimated = self.client.models.count_tokens(model=self.embedding_model, contents=batch).total_tokens, False
        except Exception:
            tokens, estimated = sum(len(text) for text in batch) // 4, True  # ~4 characters per token
        record_call(model=self.embedding_model, operation="embed", input_tokens=tokens or 0, estimated=estimated)


def _record_generation(model: str, usage) -> None:
    if usage is None:
        record_call(model=model, operation="generate", input_tokens=0, estimated=True)
        return
    thinking = usage.thoughts_token_count or 0
    record_call(
        model=model, operation="generate",
        input_tokens=(usage.prompt_token_count or 0) + (usage.tool_use_prompt_token_count or 0),
        cached_tokens=usage.cached_content_token_count or 0,
        output_tokens=(usage.candidates_token_count or 0) + thinking,
        thinking_tokens=thinking,
    )


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
