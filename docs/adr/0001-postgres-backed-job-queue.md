# ADR 0001: Durable job execution on a Postgres-backed queue

- Status: accepted (2026-10-28)
- Supersedes: the "Celery + Redis" line in `docs/ARCHITECTURE.md`

## Context

A research job runs for minutes (SEC fetches, embeddings, several LLM calls). Requirements from the Phase 3 acceptance criteria:

- `POST /api/v1/research` returns immediately.
- A job survives API restarts and worker crashes.
- Duplicate delivery is harmless; stale `running` jobs are recovered.
- Near-zero cost, one developer, a MacBook Air. Expected load: a handful of concurrent jobs, not thousands per second.

The audit reproduced two bugs that any design must close: two workers could both move one job `queued → running` (check-then-write race), and status updates were lost when the caller did not commit.

## Decision

The `research_jobs` row **is** the queue entry. No separate broker.

1. **Enqueue = insert.** The API inserts the job (`status='queued'`) and commits. The job and its "message" are one row in one transaction, so there is no DB/queue dual-write and no outbox is needed.
2. **Claim atomically with `FOR UPDATE SKIP LOCKED`.** A worker runs one statement that selects the oldest claimable job, locks it, skipping rows other workers have locked, and flips it to `running` with a fresh `lease_token`, `lease_expires_at = now() + lease`, and `attempts + 1`. Exactly one worker can win a row.
3. **Leases + heartbeat.** While a job runs, a heartbeat thread extends `lease_expires_at` every `lease/3`. A crashed worker stops heartbeating; once the lease expires the job becomes claimable again.
4. **Fencing token.** Every worker write (progress, stage output, completion) is conditioned on `lease_token = :mine`. A worker that was presumed dead (GC pause, network partition) and wakes up later finds its token replaced and its writes rejected; it aborts.
5. **Retries with backoff.** Retryable errors put the job back to `queued` with `run_after = now() + backoff(attempt)`. Permanent errors, or exhausting `max_attempts`, mark it `failed` with a human-readable `error_message`.
6. **Stage checkpoints.** Each stage records an `agent_runs` row. On a retry, stages already completed for that job are skipped, so a crash in synthesis doesn't re-download filings or re-pay for embeddings. Stage outputs are written idempotently (keyed by job; `reports.research_job_id` is UNIQUE).
7. **Wake-up by polling** (default 1 s), using a partial index on queued rows. `LISTEN/NOTIFY` is a later optimisation if latency matters.

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| FastAPI `BackgroundTasks` | Runs inside the API process. Lost on restart or crash, no retries, competes with request handling. Fails "survives API restart". |
| Celery + Redis | Mature, but adds a broker to run, monitor and pay for, plus the DB↔broker dual-write (job committed but task never enqueued, or the reverse) that needs an outbox to fix. With `acks_late` it's at-least-once, so we'd still need idempotency and fencing in Postgres. That's all the complexity of this ADR plus a second stateful system. |
| Postgres queue library (procrastinate, pgqueuer) | Reasonable. Hand-rolling ~150 lines keeps every mechanism visible and testable, which matters for a portfolio and for interviews. Revisit if the code grows. |
| Cloud queues (SQS, etc.) | Cost and a cloud dependency during local development, plus the same dual-write problem. |

## Consequences

- One stateful system (Postgres) to run, back up and reason about. Job state and queue state can't disagree.
- Throughput is bounded by Postgres row locking: fine for tens of jobs per second, far beyond our needs. Polling adds ≤1 s latency and a cheap indexed query per second per worker.
- Delivery is **at-least-once**. Exactly-once *effects* come from fencing, idempotent stage writes and unique constraints, not from the queue.

## Failure modes and recovery

| Failure | Detection | Recovery |
|---|---|---|
| API crashes after commit | n/a: the job row is durable | Worker picks it up normally |
| API crashes before commit | Client gets no response | Client retries with the same `Idempotency-Key` (ADR 0003) |
| Worker crashes mid-stage (`kill -9`, OOM, laptop sleep) | Lease expires | Another worker reclaims; completed stages are skipped |
| Worker paused, lease stolen, then resumes | Its fenced write affects 0 rows | It raises `LeaseLost` and abandons the job; the new owner continues |
| Poison job crashes the worker every time | `attempts` reaches `max_attempts` | Reaper marks it `failed` with the reason |
| External API down or rate-limited | `RetryableError` | Requeued with exponential backoff |
| DB down | Claim/heartbeat raise | Worker logs, sleeps and retries; jobs are safe in the DB |

## When we'd revisit this

- Sustained throughput where queue polling shows up in Postgres load, or a need for fan-out to many consumer types: consider a real broker.
- Jobs that must be scheduled across machines with different capabilities (GPU workers).
- Moving to a managed platform where a hosted queue costs nothing extra.

## Likely interview questions

1. **"Why not Celery?"** Celery doesn't remove the hard parts: it's at-least-once, so I still need idempotency and fencing, and it adds a broker plus a DB/broker consistency problem. With the job row as the queue entry, enqueue is atomic with job creation. I'd move to a broker when throughput or routing needs justify a second stateful system.
2. **"How does SKIP LOCKED prevent double processing?"** The claim is one `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1)`. The row lock is held until commit, and concurrent claimers skip locked rows instead of waiting, so each row has one winner. The audit reproduced the old race; `tests/integration/test_job_queue.py` proves the fix.
3. **"What if a worker freezes and comes back after its lease expired?"** Fencing token. Every write includes `WHERE lease_token = :mine`; the new owner has a different token, so the zombie's writes hit 0 rows and it aborts.
4. **"Exactly-once?"** Not on delivery, only on effects: at-least-once delivery plus idempotent, fenced writes and unique constraints (one report per job).
5. **"How do you pick the lease length?"** Long enough that heartbeats (every lease/3) survive brief hiccups, short enough that crash recovery is fast. 60 s here; the heartbeat runs on its own thread, so a long LLM call doesn't starve it.
