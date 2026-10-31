"""Tool-calling chat models for the research agent and the analyst chat (ADR 0008).

Structured one-shot steps (plan, draft, judge, synthesis) keep `GeminiClient.generate_json`. The agent's
tool loops need a LangChain chat model: it carries Gemini 3's thought signatures across tool turns and plugs
into `create_agent` middleware. Both share the process-wide pacing and map provider failures onto the job
queue's error types, so a 429 inside a researcher backs the job off exactly like one in the drafting step.
"""
from dataclasses import dataclass, field

from langchain.agents.middleware import AgentMiddleware, ModelFallbackMiddleware
from langchain_core.exceptions import ModelAuthenticationError, ModelPermissionDeniedError, ModelRateLimitError
from langchain_core.language_models import BaseChatModel

from backend.core.config import settings
from backend.llm.client import GEMINI_THROTTLE
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


def _gemini(model: str) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

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
    return ChatGoogleGenerativeAI(**kwargs)


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
