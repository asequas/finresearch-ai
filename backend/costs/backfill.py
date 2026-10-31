"""Seed the cost ledger from stage runs recorded before it existed (ADR 0009).

Run: python -m backend.costs.backfill

Older jobs kept per-stage token totals in agent_runs, not per call. Each stage becomes one ledger row, flagged
`estimated` (no cached-token split; a stage that used several models is priced at the fast model) and
`billable = false` (those jobs ran on the free tier). Embedding calls weren't counted then, so they are missing.
Jobs that already have ledger rows are skipped, so running it twice changes nothing.
"""
import sys

from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.costs.pricing import canonical_model, cost_usd
from backend.models.agent_run import AgentRun
from backend.models.llm_call import LlmCall


def backfill() -> int:
    created = 0
    with SessionLocal() as session:
        covered = set(session.scalars(select(LlmCall.research_job_id).where(LlmCall.research_job_id.is_not(None)).distinct()))
        runs = session.scalars(
            select(AgentRun).where(AgentRun.input_tokens.is_not(None)).order_by(AgentRun.started_at)
        )
        for run in runs:
            if run.research_job_id in covered:
                continue
            model = canonical_model(run.model if run.model and run.model != "multiple" else settings.gemini_fast_model)
            at = run.completed_at or run.started_at
            session.add(LlmCall(
                created_at=at, research_job_id=run.research_job_id, source="job", stage=run.agent_name, model=model,
                operation="generate", input_tokens=run.input_tokens or 0, output_tokens=run.output_tokens or 0,
                cost_usd=cost_usd(model, at, input_tokens=run.input_tokens or 0, output_tokens=run.output_tokens or 0),
                billable=False, estimated=True,
            ))
            created += 1
        session.commit()
    return created


if __name__ == "__main__":
    print(f"Added {backfill()} estimated ledger rows from earlier stage runs.")
    sys.exit(0)
