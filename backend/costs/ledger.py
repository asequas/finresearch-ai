"""Records every model call in the cost ledger (ADR 0009).

The LLM clients call `record_call` after each response, so nothing that Google bills can be missed: drafts that
fail schema validation, fallback models, researcher turns, chat answers, embeddings. Who the call was for (job,
stage, chat) comes from a context variable set by the stage runner, the agent's node wrapper and the chat service.
"""
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.costs.pricing import canonical_model, cost_usd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageScope:
    job_id: UUID | None = None
    source: str = "other"  # job, chat, other
    stage: str | None = None


_scope: ContextVar[UsageScope] = ContextVar("usage_scope", default=UsageScope())


@contextmanager
def usage_scope(*, job_id: UUID | None = None, source: str = "job", stage: str | None = None) -> Iterator[None]:
    token = _scope.set(UsageScope(job_id=job_id, source=source, stage=stage))
    try:
        yield
    finally:
        _scope.reset(token)


def _default_session_factory() -> Callable[[], Session]:
    from backend.core.database import SessionLocal

    return SessionLocal


def record_call(
    *,
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    thinking_tokens: int = 0,
    estimated: bool = False,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Write one ledger row in its own short transaction.

    Deliberately not lease-fenced: a call a zombie worker made was still billed. A failure to record is logged,
    not raised: losing a ledger row is better than failing a job that already paid for its call.
    """
    from backend.models.llm_call import LlmCall

    scope = _scope.get()
    now = datetime.now(timezone.utc)
    name = canonical_model(model)
    try:
        with (session_factory or _default_session_factory())() as session:
            session.add(LlmCall(
                created_at=now, research_job_id=scope.job_id, source=scope.source, stage=scope.stage,
                model=name, operation=operation, input_tokens=max(0, input_tokens), output_tokens=max(0, output_tokens),
                cached_tokens=max(0, cached_tokens), thinking_tokens=max(0, thinking_tokens),
                cost_usd=cost_usd(name, now, input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens),
                billable=settings.gemini_billing == "paid", estimated=estimated,
            ))
            session.commit()
    except Exception:
        logger.exception("could not record a %s call to %s in the cost ledger", operation, name)
