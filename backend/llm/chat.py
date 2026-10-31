"""Tool-calling chat models for the research agent and the analyst chat (ADR 0008).

Structured one-shot steps (plan, draft, judge, synthesis) keep `GeminiClient.generate_json`. The agent's
tool loops need a LangChain chat model: it carries Gemini 3's thought signatures across tool turns and plugs
into `create_agent` middleware. Both share the process-wide pacing and map provider failures onto the job
queue's error types, so a 429 inside a researcher backs the job off exactly like one in the drafting step.
"""
import functools
from dataclasses import dataclass, field

from langchain.agents.middleware import AgentMiddleware, ModelFallbackMiddleware
from langchain_core.exceptions import ModelAuthenticationError, ModelPermissionDeniedError, ModelRateLimitError
from langchain_core.language_models import BaseChatModel

from backend.core.config import settings
from backend.costs.budget import ensure_budget
from backend.costs.ledger import record_call
from backend.llm.client import GEMINI_THROTTLE, retry_delay_seconds
from backend.llm.pacing import COOLDOWN, DEFAULT_COOLDOWN_SECONDS, OVERLOAD_COOLDOWN_SECONDS, PACER
from backend.pipeline.base import (
    CancelRequested,
    LeaseLost,
    PermanentError,
    ProviderBusyError,
    RetryableError,
    ShutdownRequested,
)

# Errors that belong to the job (queue backoff, cancel, lease), never to the model.
JOB_ERRORS = (PermanentError, RetryableError, LeaseLost, CancelRequested, ShutdownRequested)


def provider_error(exc: BaseException) -> BaseException:
    """Translate a model failure into the queue's vocabulary: busy (minutes), retryable, or permanent."""
    if isinstance(exc, JOB_ERRORS):
        return exc
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(exc, (ModelAuthenticationError, ModelPermissionDeniedError)) or code in (401, 403):
        return PermanentError("The Gemini API key was rejected. Check GEMINI_API_KEY in .env.")
    if isinstance(exc, ModelRateLimitError) or code == 429:
        return ProviderBusyError("Gemini's quota is used up for now. The job will resume where it stopped.")
    if isinstance(code, int) and code >= 500:
        return ProviderBusyError(f"Gemini is overloaded (HTTP {code}). This usually clears within minutes.")
    return RetryableError(f"Model call failed: {type(exc).__name__}: {str(exc)[:300]}")


class GeminiGuard(AgentMiddleware):
    """Outermost model middleware: pace requests, then translate whatever the fallback chain gave up on."""

    def wrap_model_call(self, request, handler):
        GEMINI_THROTTLE.wait()
        try:
            return handler(request)
        except Exception as exc:
            mapped = provider_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc


class ModelCoolingDown(ProviderBusyError):
    """Raised without a network call when a model is in cool-down, so the fallback chain moves on at once."""


def record_chat_usage(model: str, message) -> None:
    usage = getattr(message, "usage_metadata", None) or {}
    details_in = usage.get("input_token_details") or {}
    details_out = usage.get("output_token_details") or {}
    record_call(
        model=model, operation="generate", input_tokens=usage.get("input_tokens", 0),
        cached_tokens=details_in.get("cache_read", 0) or 0, output_tokens=usage.get("output_tokens", 0),
        thinking_tokens=details_out.get("reasoning", 0) or 0, estimated=not usage,
    )


@functools.cache
def _paced_class():
    """ChatGoogleGenerativeAI that checks the budget, honours cool-downs and pacing, and records every response."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    class PacedGemini(ChatGoogleGenerativeAI):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            ensure_budget()
            if (wait := COOLDOWN.remaining(self.model)) > 0:
                raise ModelCoolingDown(f"{self.model} is cooling down for {wait:.0f}s after a rate limit.")
            PACER.acquire(self.model)
            try:
                result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if code == 429:
                    COOLDOWN.cool(self.model, retry_delay_seconds(exc, DEFAULT_COOLDOWN_SECONDS))
                elif code in (500, 503, 504):
                    COOLDOWN.cool(self.model, OVERLOAD_COOLDOWN_SECONDS)
                raise
            for generation in result.generations:
                record_chat_usage(self.model, generation.message)
            return result

    return PacedGemini


def _gemini(model: str) -> BaseChatModel:
    if not settings.gemini_api_key:
        raise PermanentError("GEMINI_API_KEY is not configured. Add it to .env to run research jobs.")
    kwargs = dict(
        model=model,
        google_api_key=settings.gemini_api_key,
        # No temperature: Gemini 3 models use fixed sampling and warn when one is sent.
        max_retries=0,  # retries belong to the job queue, where they are visible
        timeout=settings.gemini_timeout_seconds,
    )
    if "lite" not in model:
        kwargs["thinking_level"] = settings.gemini_thinking_level
    return _paced_class()(**kwargs)


@dataclass
class AgentModel:
    """A chat model plus the middleware that makes it production-safe (pacing, fallbacks, error mapping)."""

    model: BaseChatModel
    middleware: list[AgentMiddleware] = field(default_factory=list)
    name: str = ""


def gemini_agent_model(strong: bool = False) -> AgentModel:
    preferred = settings.gemini_strong_model if strong else settings.gemini_fast_model
    fallbacks = settings.gemini_strong_fallbacks if strong else settings.gemini_fast_fallbacks
    chain = [preferred, *[m for m in fallbacks if m != preferred]]
    middleware: list[AgentMiddleware] = [GeminiGuard()]
    if len(chain) > 1:
        middleware.append(ModelFallbackMiddleware(*[_gemini(m) for m in chain[1:]]))
    return AgentModel(model=_gemini(chain[0]), middleware=middleware, name=chain[0])
