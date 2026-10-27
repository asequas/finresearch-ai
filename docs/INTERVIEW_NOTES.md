# Interview Notes

Things I should be able to explain, each linked to the code or ADR that demonstrates it. Add an entry whenever a decision or bug teaches something defensible.

## Transactions and persistence

- **`flush()` is not `commit()`.** Flush sends SQL inside the open transaction; closing the session without commit rolls it back. POST once returned 201 and the next GET returned 404 for exactly this reason. Fixed for create in `backend/services/research_job.py:28`. The same bug still exists in `update_status` / `update_progress` (STATUS D1): the fix was applied to one method, not to the rule.
- **Who owns the transaction?** Repositories flush; services commit. When the rule is enforced in one place but tests commit on the service's behalf, the test suite hides violations. Lesson: tests should exercise the same session lifecycle that production callers use.
- **Row locks last until the transaction ends.** During the audit, one thread holding an uncommitted UPDATE blocked a second UPDATE on the same row, a self-deadlock in a single thread. The lock-holder must commit or roll back before anyone else can write that row.

## Concurrency and state machines

- **Check-then-act is a race.** Reading `status == queued` in Python and then writing `running` lets two workers both "win" under READ COMMITTED (reproduced, STATUS D2). Transitions that guard against duplicates have to be atomic in the database. The exact mechanism is pending the Phase 3 ADR.
- **State without timestamps is half a state machine.** A `completed` job with no `completed_at` and a `failed` job with no `error_message` can't be debugged or shown to a user (STATUS D4).

## Schema design

- **App validation is not data integrity.** Pydantic and Python enums only guard the paths that go through them. With no CHECK constraint the DB accepted `status='banana'`, and the next ORM read crashed (STATUS D5). Enforce invariants in the database too.
- **Enum storage trade-off.** A native PG enum is strict, but adding values needs a migration (and before PG 12 couldn't run inside a transaction). `VARCHAR` + CHECK is flexible and still strict. `VARCHAR` with nothing is neither. Decision pending (STATUS open decisions).
- **Suppressing a migration-drift check hides real drift.** `database/migrations/env.py:75-80` makes `alembic check` look clean for `research_jobs.status`.
- **Never edit an applied migration.** Schema changes go in new revisions; `411c859e2482` is frozen.
- **Embedding dimension is a schema constraint.** `document_chunks.embedding` is `vector(768)` (`backend/models/document_chunk.py:48`); changing models means a migration plus re-embedding.
- **Money uses `Decimal` / `Numeric`, never float.** The DB uses `Numeric`, but the model annotations still say `float` (STATUS D13).
- **Unique constraints as idempotency guards.** `reports.research_job_id` is UNIQUE (`backend/models/report.py:24-29`), so a duplicate pipeline run can't create a second report; it either fails or must upsert. Trade-off: no report versioning.
- **Timezone-aware timestamps.** `datetime.now(timezone.utc)`, not `utcnow()`. Server-side defaults are still missing (STATUS D12).

## Testing

- **Integration tests caught the flush bug.** Unit tests with mocks wouldn't have.
- **Test isolation.** Tests that write to the dev DB and never clean up pollute the data that later tests (stale-job recovery, "list my jobs") depend on, and can't run in parallel (STATUS D3).

## Security

- **A UUID is not authorization.** Unguessable IDs reduce the risk but don't remove it: IDs leak through logs, URLs and shared links. Every read checks ownership (STATUS D8).
- **Dev identity is not auth**, and it shouldn't commit inside a dependency or race on creation (STATUS D9).
