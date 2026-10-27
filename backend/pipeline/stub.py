"""Phase 3 stub pipeline: real stage names, fake work. Used for queue tests and demos."""
import os
import time
from dataclasses import dataclass

from backend.models.research_job import ResearchStage
from backend.pipeline.base import JobContext


@dataclass
class SleepStage:
    name: ResearchStage
    weight: int = 1
    seconds: float = 0.0

    def run(self, ctx: JobContext) -> None:
        deadline = time.monotonic() + self.seconds
        while time.monotonic() < deadline:
            ctx.checkpoint()
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def stub_stages() -> list[SleepStage]:
    seconds = float(os.environ.get("STUB_STAGE_SECONDS", "1.5"))
    return [SleepStage(name=stage, seconds=seconds) for stage in ResearchStage]
