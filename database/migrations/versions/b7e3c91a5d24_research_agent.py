"""research agent: graph stages, LangGraph checkpoint tables, report chat

Revision ID: b7e3c91a5d24
Revises: 04df74fe3a5f
Create Date: 2026-10-31 11:00:00

The checkpoint tables are langgraph-checkpoint-postgres 3.2.0's schema (its migrations 0-9), frozen here so
Alembic owns every table in the database. The migration versions are recorded in checkpoint_migrations, so
PostgresSaver.setup() finds nothing to do. A library upgrade that adds a migration gets its own revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7e3c91a5d24"
down_revision: Union[str, Sequence[str], None] = "04df74fe3a5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STAGES = (
    "resolving_company", "fetching_filings", "extracting_financials", "computing_metrics",
    "indexing_documents", "analyzing", "verifying", "synthesizing",
)
NEW_STAGES = (
    "resolving_company", "fetching_filings", "extracting_financials", "computing_metrics",
    "indexing_documents", "analyzing", "planning", "researching", "drafting", "verifying", "synthesizing",
)

CHECKPOINT_SCHEMA = [
    "CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY)",
    """CREATE TABLE checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        parent_checkpoint_id TEXT,
        type TEXT,
        checkpoint JSONB NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    )""",
    """CREATE TABLE checkpoint_blobs (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        channel TEXT NOT NULL,
        version TEXT NOT NULL,
        type TEXT NOT NULL,
        blob BYTEA,
        PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
    )""",
    """CREATE TABLE checkpoint_writes (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        idx INTEGER NOT NULL,
        channel TEXT NOT NULL,
        type TEXT,
        blob BYTEA NOT NULL,
        task_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
    )""",
    "CREATE INDEX checkpoints_thread_id_idx ON checkpoints(thread_id)",
    "CREATE INDEX checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)",
    "CREATE INDEX checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)",
    "INSERT INTO checkpoint_migrations (v) SELECT generate_series(0, 9)",
]


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.drop_constraint("ck_research_jobs_current_stage", "research_jobs", type_="check")
    op.create_check_constraint(
        "ck_research_jobs_current_stage", "research_jobs",
        f"current_stage IS NULL OR current_stage IN ({_in(NEW_STAGES)})",
    )

    for statement in CHECKPOINT_SCHEMA:
        op.execute(statement)

    op.create_table(
        "report_chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_job_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_report_chat_messages_role"),
        sa.ForeignKeyConstraint(["research_job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_chat_messages_job_created", "report_chat_messages", ["research_job_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_report_chat_messages_job_created", table_name="report_chat_messages")
    op.drop_table("report_chat_messages")
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations"):
        op.execute(f"DROP TABLE {table}")
    op.execute(
        f"UPDATE research_jobs SET current_stage = 'analyzing' "
        f"WHERE current_stage IN ('planning', 'researching', 'drafting')"
    )
    op.drop_constraint("ck_research_jobs_current_stage", "research_jobs", type_="check")
    op.create_check_constraint(
        "ck_research_jobs_current_stage", "research_jobs",
        f"current_stage IS NULL OR current_stage IN ({_in(OLD_STAGES)})",
    )
