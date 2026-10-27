# ADR 0002: Research job state machine

- Status: accepted (2026-10-28)

## Context

The original model had `queued → running → completed | failed`, enforced only in Python, with no timestamps set, no reason on failure, and no database constraint (the audit stored `status='banana'`). Phase 3 adds retries, crash recovery and cancellation.

## Decision

Statuses (`VARCHAR(32)` + CHECK, see ADR 0004): `queued`, `running`, `completed`, `failed`, `cancelled`.

| From | To | Trigger | Side effects |
|---|---|---|---|
| (new) | queued | `POST /research` | `attempts=0`, `run_after=now()` |
| queued | running | worker claim | new `lease_token`, `attempts+1`, `started_at` set on first claim |
| running | running | lease expired, reclaimed | new token, `attempts+1` (the old owner is fenced out) |
| running | completed | last stage done | `progress=100`, `completed_at`, lease cleared |
| running | queued | retryable error, attempts left | `run_after = now() + backoff`, `error_message` = last error |
| running | failed | permanent error, attempts exhausted, or reaped | `completed_at`, human-readable `error_message` |
| queued | cancelled | user cancel | `completed_at` |
| running | cancelled | user cancel → `cancel_requested=true`; worker stops at the next stage boundary | `completed_at` |
| failed, cancelled | queued | user retry | `attempts=0`, error cleared; completed stage checkpoints are reused |

`completed` is terminal. Every transition is a single conditional `UPDATE … WHERE status = :expected [AND lease_token = :token]`, so an illegal or stale transition updates 0 rows instead of corrupting state.

Progress is monotonic per attempt and derived from stage weights. `current_stage` is one of the pipeline stages (CHECK constraint).

## Alternatives

- **More statuses** (`retrying`, `stale`): these are derivable (`queued` with `attempts>0`; `running` with an expired lease). Fewer states mean fewer transitions to test.
- **State machine library**: overkill for nine transitions; the SQL conditional updates are the real enforcement.

## Consequences

The UI can show "retrying (attempt 2/3)" from `attempts` and `error_message` without extra states. User retry is "safe" because stages are idempotent and checkpointed.

## Failure modes

- Cancel during a long LLM call: honoured at the next stage boundary or heartbeat, not instantly. Acceptable; documented in the UI.
- A clock skew between the API and DB: all time comparisons use the database `now()`.

## Interview questions

1. *"How do you prevent an invalid transition under concurrency?"* Put the expected current state in the `WHERE` clause; 0 rows updated means someone else moved it.
2. *"Why can a user retry a failed job safely?"* Stages are idempotent and checkpointed, and the report is unique per job.
3. *"Why no `retrying` status?"* It's derivable; every extra state multiplies transitions and tests.
