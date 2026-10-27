"""Provider-agnostic LLM adapter (ADR 0006): structured JSON generation + embeddings."""
import math
import threading
import time
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from backend.core.config import settings
from backend.models.document_chunk import EMBEDDING_DIMENSION
from backend.pipeline.base import PermanentError, RetryableError

T = TypeVar("T", bound=BaseModel)


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


class GeminiClient:
    """Gemini via google-genai. 429/5xx become RetryableError so the job queue backs off."""

    def __init__(self, api_key: str | None = None):
        from google import genai

        key = api_key or settings.gemini_api_key
        if not key:
            raise PermanentError("GEMINI_API_KEY is not configured. Add it to .env to run research jobs.")
        self.client = genai.Client(api_key=key)
        self.fast_model = settings.gemini_fast_model
        self.strong_model = settings.gemini_strong_model
        self.embedding_model = settings.gemini_embedding_model
        self.throttle = _Throttle(min_interval=1.0)

    def _call(self, fn, *args, **kwargs):
        from google.genai import errors

        self.throttle.wait()
        try:
            return fn(*args, **kwargs)
        except errors.APIError as exc:
            if exc.code in (429, 500, 502, 503, 504):
                raise RetryableError(f"Gemini API {exc.code}: {exc.message}") from exc
            if exc.code in (401, 403):
                raise PermanentError("The Gemini API key was rejected. Check GEMINI_API_KEY in .env.") from exc
            raise RetryableError(f"Gemini API {exc.code}: {exc.message}") from exc
        except Exception as exc:  # network errors from the transport layer
            raise RetryableError(f"Gemini request failed: {type(exc).__name__}: {exc}") from exc

    def generate_json(
        self, *, prompt: str, schema: type[T], system: str, strong: bool = False, temperature: float = 0.2
    ) -> LLMResult[T]:
        from google.genai import types

        model = self.strong_model if strong else self.fast_model
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        last_error: Exception | None = None
        for _ in range(2):  # one repair attempt for malformed output
            response = self._call(self.client.models.generate_content, model=model, contents=prompt, config=config)
            usage = response.usage_metadata
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

    def embed(self, texts: list[str], *, task: str) -> list[list[float]]:
        from google.genai import types

        task_type = "RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT"
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 100):
            batch = texts[start : start + 100]
            response = self._call(
                self.client.models.embed_content,
                model=self.embedding_model,
                contents=batch,
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMENSION),
            )
            # Gemini only normalises full-size (3072-d) embeddings; truncated ones must be renormalised.
            vectors.extend(normalise(list(embedding.values)) for embedding in response.embeddings)
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMENSION for v in vectors):
            raise RetryableError("Embedding response had the wrong shape")
        return vectors


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
