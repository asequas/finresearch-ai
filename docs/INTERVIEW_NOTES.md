# Interview Notes

Things I should be able to explain, each linked to the code or ADR that demonstrates it. Add an entry whenever a decision or bug teaches something defensible.

## Practice first (answer before reading ADR 0001)

> "A research request may take several minutes. How would you design the system so the HTTP request returns quickly,
> the job survives application restarts, and the worker can recover from failures?"

Write your answer, then compare it with [ADR 0001](adr/0001-postgres-backed-job-queue.md) and
[ADR 0002](adr/0002-job-state-machine.md). Each ADR ends with likely follow-up questions.

## Transactions and persistence

- **`flush()` is not `commit()`.** Flush sends SQL inside the open transaction; closing the session without commit rolls it back. POST once returned 201 and the next GET returned 404 for exactly this reason. The audit found the fix had been applied to one method, not to the rule: `update_status` / `update_progress` still lost their changes. Fixed for good by moving every worker write into `JobQueueService`, where each operation commits its own short transaction.
- **Who owns the transaction?** Repositories flush; services commit. When the rule is enforced in one place but tests commit on the service's behalf, the test suite hides violations. Lesson: tests should exercise the same session lifecycle that production callers use.
- **Row locks last until the transaction ends.** During the audit, one thread holding an uncommitted UPDATE blocked a second UPDATE on the same row, a self-deadlock in a single thread. The lock-holder must commit or roll back before anyone else can write that row.

## Concurrency and state machines

- **Check-then-act is a race.** Reading `status == queued` in Python and then writing `running` lets two workers both "win" under READ COMMITTED (reproduced in the audit). Transitions must be atomic in the database: a conditional `UPDATE … WHERE status = :expected`, plus `FOR UPDATE SKIP LOCKED` for claims (ADR 0001, 0002).
- **State without timestamps is half a state machine.** A `completed` job with no `completed_at` and a `failed` job with no `error_message` can't be debugged or shown to a user.

## Schema design

- **App validation is not data integrity.** Pydantic and Python enums only guard the paths that go through them. With no CHECK constraint the DB accepted `status='banana'`, and the next ORM read crashed. Enforce invariants in the database too.
- **Enum storage trade-off.** A native PG enum is strict, but adding values needs a migration (and before PG 12 couldn't run inside a transaction). `VARCHAR` + CHECK is flexible and still strict. `VARCHAR` with nothing is neither. Decided: VARCHAR + CHECK ([ADR 0004](adr/0004-enum-storage.md)).
- **Suppressing a migration-drift check hides real drift.** The original `env.py` exemption made `alembic check` look clean for `research_jobs.status`; it was removed with the CHECK-constraint migration.
- **Never edit an applied migration.** Schema changes go in new revisions; `411c859e2482` is frozen.
- **Embedding dimension is a schema constraint.** `document_chunks.embedding` is `vector(768)` (`backend/models/document_chunk.py:48`); changing models means a migration plus re-embedding.
- **Money uses `Decimal` / `Numeric`, never float.** The DB uses `Numeric`, and the model annotations now say `Decimal` too.
- **Unique constraints as idempotency guards.** `reports.research_job_id` is UNIQUE (`backend/models/report.py:24-29`), so a duplicate pipeline run can't create a second report; it either fails or must upsert. Trade-off: no report versioning.
- **Timezone-aware timestamps.** `datetime.now(timezone.utc)`, not `utcnow()`. Server-side defaults were added so raw SQL inserts work too.

## Testing

- **Integration tests caught the flush bug.** Unit tests with mocks wouldn't have.
- **Test isolation.** Tests that write to the dev DB and never clean up pollute the data that later tests (stale-job recovery, "list my jobs") depend on, and can't run in parallel. Fixed with a dedicated `*_test` database and per-test truncation (`tests/conftest.py`).

## Security

- **A UUID is not authorization.** Unguessable IDs reduce the risk but don't remove it: IDs leak through logs, URLs and shared links. Every read is scoped to the owner, and another user's job returns 404, indistinguishable from a missing one.
- **Dev identity is not auth.** It is now race-safe (`INSERT … ON CONFLICT DO NOTHING`), and swapping in real auth changes one dependency.

## Durable background execution (ADR 0001, 0002)

- **The job row is the queue entry.** Creating the job and enqueuing it are one INSERT in one transaction, so the
  DB/queue dual-write problem (and the outbox pattern that fixes it) never arises. `backend/services/research_job.py` `submit`.
- **`FOR UPDATE SKIP LOCKED`** makes claiming atomic and non-blocking: one statement selects, locks and flips the
  row. Proof: ten threads race for one job and exactly one wins (`tests/integration/test_job_queue.py`).
- **Leases, heartbeats and fencing tokens.** A crashed worker's lease expires and another reclaims the job; a worker
  that was paused and lost its lease finds every write conditioned on its old token affects 0 rows. Proof: a real
  `kill -9` test and a zombie-write test (`tests/integration/test_worker.py`).
- **At-least-once delivery, exactly-once effects.** Stages write idempotently (delete-then-insert per job, upserts,
  `reports.research_job_id` UNIQUE) and are checkpointed, so a retry resumes after the last completed stage.
- **Retryable vs permanent errors.** A 429 from Gemini is retried with exponential backoff and jitter; "ticker not
  found" fails immediately with a readable reason. Unknown errors are retried until the attempt budget runs out.
- **Graceful shutdown** releases the job without spending an attempt (SIGTERM test).

## API contract (ADR 0003)

- **201 vs 202**: 202 means accepted for processing; the `Location` header points at the job.
- **Idempotency keys**: one per user intent (form instance), unique per user in the DB; same key + different
  payload → 409 via a request fingerprint; concurrent duplicates resolved by catching the unique violation.
- **Cursor pagination** on `(created_at, id)`: stable under inserts, unlike offset paging.

## Trustworthy AI output (ADR 0005, 0006)

- **Facts / calculations / interpretations** are separate claim types with different verification rules.
- **The LLM never does arithmetic**: numbers come from XBRL or tested `Decimal` formulas; the model cites metric
  ids; `backend/analysis/verification.py` checks every number in a calculation claim against its metric.
- **Literal quote verification** before any LLM judge: cheap, deterministic, and catches fabricated evidence.
- **Hybrid retrieval with RRF**: vectors find meaning, full-text finds exact financial terms; reciprocal rank fusion
  combines rankings without calibrating scores. Both run in Postgres (`backend/analysis/retrieval.py`).
- **Why no LangGraph (yet)**: the workflow is linear; durability already lives in the queue. Two checkpointing
  systems would have to be kept consistent. Adopt it when routing becomes dynamic.
- **Reproducibility under restatement**: each job snapshots the figures it used with XBRL provenance.
- **Evaluation**: automatic coverage, quote-verification and numeric-consistency rates per report, plus a
  human-labelled citation-correctness score against a 95% target (`backend/evals/citations.py`).

## Frontend

- **Typed client generated from OpenAPI** (`npm run api:types`, `api:check`): backend changes that break the
  frontend fail the build instead of failing in production.
- **Polling vs SSE/WebSockets**: polling every 1.5 s while a job is active is simple, cache-friendly and enough for
  minutes-long jobs; push would matter for many concurrent viewers or sub-second updates.
- **Designed states**: loading bars at the real size (no layout shift), empty frames with one sentence, errors inside
  the failing block with Retry, partial results (failed stages, skipped metrics, unsupported claims) shown, not hidden.
