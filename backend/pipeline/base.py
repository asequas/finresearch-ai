"""Building blocks shared by every pipeline stage."""
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.research_job import ResearchStage
from backend.repositories.research_job import ResearchJobRepository


class RetryableError(Exception):
    """Transient failure (network, rate limit, 5xx). The job is retried with backoff."""


class PermanentError(Exception):
    """Failure that retrying cannot fix. The message is shown to the user."""


class LeaseLost(Exception):
    """Another worker owns this job now; stop without writing anything else."""


class CancelRequested(Exception):
    pass


class ShutdownRequested(Exception):
    pass


@dataclass
class StageUsage:
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: Decimal = Decimal("0")
    metadata: dict = field(default_factory=dict)

    def add_llm_call(
        self, *, model: str, input_tokens: int, output_tokens: int, cost: Decimal = Decimal("0")
    ) -> None:
        self.model = model if self.model in (None, model) else "multiple"
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.estimated_cost += cost


@dataclass
class JobContext:
    job_id: UUID
    lease_token: UUID
    attempt: int
    query: str
    company: str
    ticker: str
    session_factory: Callable[[], Session]
    cancel_event: threading.Event = field(default_factory=threading.Event)
    lease_lost_event: threading.Event = field(default_factory=threading.Event)
    shutdown_event: threading.Event = field(default_factory=threading.Event)
    usage: StageUsage = field(default_factory=StageUsage)

    def checkpoint(self) -> None:
        """Called at stage boundaries and inside long loops."""
        if self.lease_lost_event.is_set():
            raise LeaseLost(f"Lease lost for job {self.job_id}")
        if self.cancel_event.is_set():
            raise CancelRequested()
        if self.shutdown_event.is_set():
            raise ShutdownRequested()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """A fenced write transaction: commits only while this worker still holds the lease.

        The job row is locked FOR UPDATE first, so a reclaim can't interleave
        with our writes; if the token no longer matches we write nothing.
        """
        with self.session_factory() as session:
            if not ResearchJobRepository().assert_lease(
                session, job_id=self.job_id, lease_token=self.lease_token
            ):
                session.rollback()
                self.lease_lost_event.set()
                raise LeaseLost(f"Lease lost for job {self.job_id}")
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise


class Stage(Protocol):
    name: ResearchStage
    weight: int

    def run(self, ctx: JobContext) -> None: ...
