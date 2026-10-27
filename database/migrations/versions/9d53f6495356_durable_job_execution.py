"""durable job execution: leases, retries, idempotency, state constraints

See docs/adr/0001-0004.

Revision ID: 9d53f6495356
Revises: 411c859e2482
Create Date: 2026-10-28 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9d53f6495356"
down_revision: Union[str, Sequence[str], None] = "411c859e2482"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = ("queued", "running", "completed", "failed", "cancelled")
STAGES = (
    "resolving_company",
    "fetching_filings",
    "extracting_financials",
    "computing_metrics",
    "indexing_documents",
    "analyzing",
    "verifying",
    "synthesizing",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    # Jobs left "running" before leases existed can never be recovered; close them out.
    op.execute(
        "UPDATE research_jobs SET status = 'failed', "
        "error_message = 'Abandoned before durable execution existed', "
        "completed_at = now() WHERE status = 'running'"
    )
    # Old stage names are not valid any more; no code ever set them.
    op.execute("UPDATE research_jobs SET current_stage = NULL")

    op.add_column("research_jobs", sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("research_jobs", sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False))
    op.add_column(
        "research_jobs",
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("research_jobs", sa.Column("lease_token", sa.UUID(), nullable=True))
    op.add_column("research_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "research_jobs",
        sa.Column("cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("research_jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("research_jobs", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.add_column(
        "research_jobs",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.alter_column("research_jobs", "status", server_default="queued")
    op.alter_column("research_jobs", "progress", server_default=sa.text("0"))
    op.alter_column("research_jobs", "created_at", server_default=sa.text("now()"))

    op.create_check_constraint("ck_research_jobs_status", "research_jobs", f"status IN ({_in(STATUSES)})")
    op.create_check_constraint(
        "ck_research_jobs_current_stage",
        "research_jobs",
        f"current_stage IS NULL OR current_stage IN ({_in(STAGES)})",
    )
    op.create_check_constraint("ck_research_jobs_progress", "research_jobs", "progress BETWEEN 0 AND 100")
    op.create_check_constraint(
        "ck_research_jobs_attempts", "research_jobs", "attempts >= 0 AND max_attempts >= 1"
    )

    # A status-only index is low-selectivity; the worker needs "claimable" and "expired lease" lookups.
    op.drop_index("ix_research_jobs_status", table_name="research_jobs")
    op.create_index(
        "ix_research_jobs_claimable",
        "research_jobs",
        ["run_after", "created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_research_jobs_lease",
        "research_jobs",
        ["lease_expires_at"],
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "uq_research_jobs_user_idempotency_key",
        "research_jobs",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column("agent_runs", sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False))
    op.create_check_constraint(
        "ck_agent_runs_status", "agent_runs", "status IN ('running', 'completed', 'failed')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.drop_column("agent_runs", "attempt")

    op.drop_index("uq_research_jobs_user_idempotency_key", table_name="research_jobs")
    op.drop_index("ix_research_jobs_lease", table_name="research_jobs")
    op.drop_index("ix_research_jobs_claimable", table_name="research_jobs")
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"], unique=False)

    for name in (
        "ck_research_jobs_attempts",
        "ck_research_jobs_progress",
        "ck_research_jobs_current_stage",
        "ck_research_jobs_status",
    ):
        op.drop_constraint(name, "research_jobs", type_="check")

    op.alter_column("research_jobs", "created_at", server_default=None)
    op.alter_column("research_jobs", "progress", server_default=None)
    op.alter_column("research_jobs", "status", server_default=None)

    for column in (
        "updated_at",
        "request_fingerprint",
        "idempotency_key",
        "cancel_requested",
        "lease_expires_at",
        "lease_token",
        "run_after",
        "max_attempts",
        "attempts",
    ):
        op.drop_column("research_jobs", column)
