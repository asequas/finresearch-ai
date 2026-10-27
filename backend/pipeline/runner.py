"""Runs an ordered list of stages for one claimed job, with checkpoints."""
import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from backend.pipeline.base import JobContext, LeaseLost, Stage, StageUsage
from backend.services.job_queue import JobQueueService

logger = logging.getLogger(__name__)


def run_pipeline(ctx: JobContext, stages: Sequence[Stage], queue: JobQueueService) -> None:
    """Run every stage not already completed for this job (from any attempt).

    Stages must be idempotent: a crash after a stage's outputs commit but
    before its checkpoint is recorded means the stage runs again.
    """
    completed = queue.completed_stages(ctx.job_id)
    total_weight = sum(stage.weight for stage in stages) or 1
    done_weight = sum(stage.weight for stage in stages if stage.name.value in completed)

    for stage in stages:
        if stage.name.value in completed:
            logger.info("job %s: skipping %s (checkpointed)", ctx.job_id, stage.name.value)
            continue

        ctx.checkpoint()
        progress = min(99, done_weight * 100 // total_weight)
        if not queue.set_stage(ctx.job_id, ctx.lease_token, stage=stage.name, progress=progress):
            raise LeaseLost(f"Lease lost for job {ctx.job_id}")

        run_id = queue.start_stage_run(ctx.job_id, ctx.lease_token, stage=stage.name, attempt=ctx.attempt)
        if run_id is None:
            raise LeaseLost(f"Lease lost for job {ctx.job_id}")

        started = datetime.now(timezone.utc)
        ctx.usage = StageUsage()
        logger.info("job %s: running %s (attempt %d)", ctx.job_id, stage.name.value, ctx.attempt)
        try:
            stage.run(ctx)
        except BaseException as exc:
            queue.finish_stage_run(
                run_id,
                status="failed",
                started=started,
                error_message=f"{type(exc).__name__}: {exc}"[:2000],
                **_usage(ctx.usage),
            )
            raise

        queue.finish_stage_run(run_id, status="completed", started=started, **_usage(ctx.usage))
        done_weight += stage.weight


def _usage(usage: StageUsage) -> dict:
    return {
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "estimated_cost": usage.estimated_cost,
        "metadata": usage.metadata,
    }
