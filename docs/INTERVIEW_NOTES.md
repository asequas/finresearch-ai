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

## Retrieval and reranking (ADR 0007)

- **Measure before optimising.** A 30-question gold set showed the "hybrid" search was worse than vector-only:
  the keyword side matched the company's own name in every chunk. Dropping it and halving the keyword weight fixed
  hybrid; the eval made that visible (`python -m backend.evals.retrieval`).
- **Bi-encoder vs cross-encoder.** Cheap first stage for recall (embeddings + full-text, RRF), expensive cross-encoder
  for precision on the top 20 only.
- **Model/data mismatch.** An MS MARCO cross-encoder on 2,200-character chunks made results worse until each chunk
  was scored by its best 450-character window.
- **Fuse, don't replace.** Replacing the ranking raised R@1 but lost recall; RRF over both rankings kept both.
- **Labels that survive re-indexing.** Relevance = the chunk contains a verified answer phrase, not a chunk id.

## Agentic research on LangGraph (ADR 0008)

- **Agents where routing is dynamic, code where it isn't.** Fetching filings and computing metrics stay plain code;
  only "where should I look next?" became an agent loop. The critic that decides whether to re-research is an `if`
  over verifier verdicts, not a model ([`backend/agent/graph.py`](../backend/agent/graph.py)).
- **Fan-out/fan-in with `Send` and a reducer.** Each planned question goes to its own researcher; `findings` is an
  `operator.add` channel so parallel results merge instead of overwriting. The draft node runs once every researcher
  in the superstep has finished.
- **Bounded self-correction.** Material claims that fail verification go back to a targeted researcher with the
  verifier's reason. Budgets: one revision round, 6 tool calls and 8 model calls per researcher, at most 6 researchers.
- **Two checkpointers, one owner each.** The queue row owns the job (lease, attempts, cancel); `PostgresSaver` owns the
  position inside the graph. Side effects are lease-fenced, so the unfenced checkpoint can only cause a redo. Tested:
  a 429 in one researcher resumes the graph without re-running the researchers that finished
  ([`tests/integration/test_research_agent.py`](../tests/integration/test_research_agent.py)).
- **Grounding the agent.** Researchers can only cite passage handles a tool returned (others are dropped and logged);
  quotes are checked verbatim in code; the chat agent's citations go through the same check and are shown as verified
  or not.
- **Retries belong to one layer.** LangChain's model client runs with `max_retries=0`; provider errors are mapped to
  the queue's busy/retryable/permanent types by a middleware, so backoff is visible and bounded in one place.
- **Observability without new infra.** Every node and researcher is an `agent_runs` row with its tool calls; the job
  page renders them live from `GET /research/{id}/trace`.
- **The chat's record is a table, not a checkpointer.** One source of truth; the agent is rebuilt from recent turns per
  question, and the question and answer commit together.

## Intrinsic value: a deterministic DCF (ADR 0010)

- **Numbers from code, words from the model.** FCFF DCF in Decimal ([`backend/valuation/dcf.py`](../backend/valuation/dcf.py)).
  Its outputs are `dcf_*` metrics the drafter cites and the verifier checks (to the cent for value per share).
- **Test against a published example.** The engine reproduces Damodaran's 3M valuation, $86.92 against $86.95 a
  share, the gap being the book's rounding ([`tests/unit/test_dcf.py`](../tests/unit/test_dcf.py)).
- **Bottom-up beta without prices.** Industry unlevered beta relevered at the industry D/E; synthetic rating from
  interest coverage gives the default spread; the Treasury 10-year is the risk-free rate.
- **Growth must be paid for.** Reinvestment = g ÷ ROC; with stable ROC = cost of capital, extra stable growth adds
  almost nothing, as the sensitivity grid shows.
- **Consistency bug found by inspecting results.** Operating leases are inside operating income under ASC 842, so
  subtracting them as debt double-counted $89B at Amazon.
- **Reproducible what-ifs.** Stored inputs with sources and dates, a versioned calculation, and overrides that start
  from the stored inputs and save nothing.
- **Don't tune towards the price; find the bias** (ADR 0011). Every v1 value was below market; changing one
  assumption at a time traced it to expensed R&D, a 5-year horizon for everyone, and no excess returns forever. All
  three were fixed as Damodaran does, and the remaining gaps are shown as implied vs assumed growth (reverse DCF).

## Fair value: three simple methods and a free delayed price (ADR 0012)

- **Several simple methods beat one elaborate model when trust matters.** A cash-flow DCF, earnings power value (no
  growth) and a reverse DCF each answer a different question; the range between them is honest uncertainty
  ([`backend/valuation/fair_value.py`](../backend/valuation/fair_value.py)).
- **Normalise margins, not dollars.** A 3-year dollar average undervalued a 4× grower; the average FCF margin on
  the latest revenue keeps the smoothing ([`assumptions.py`](../backend/valuation/assumptions.py),
  [`test_fair_value_defaults.py`](../tests/unit/test_fair_value_defaults.py)).
- **Stock compensation is a cost.** Deducted from free cash flow; $12B a year at Microsoft.
- **Free data, honest licensing.** Cboe's keyless delayed quote is personal-use only: labelled in the UI, cached,
  isolated behind one function, and a typed price always works ([`price.py`](../backend/valuation/price.py)).
- **When the model disagrees with the market, quantify it rather than tune it.** All six covered names need 22%+
  annual FCF growth to justify their prices against 3-14% records; raising long-run growth to the risk-free rate
  closes less than half the gap.
- **Injectable dependencies keep tests offline.** The valuation service takes a price fetcher via FastAPI
  `Depends`, so tests drive "below range" and "above range" without the network.

## CI/CD (ADR 0013)

- **Ship what you tested.** CI boots the production compose file from the images it built and runs a research job
  through nginx, then pushes exactly those images, tagged by commit ([`ci.yml`](../.github/workflows/ci.yml)).
- **Native multi-arch builds.** amd64 and arm64 on GitHub's free runners, joined into one tag; the free Oracle VM is ARM.
- **Migrations before traffic, rollback by tag.** A one-shot `migrate` service gates the API and worker;
  [`deploy.sh`](../deploy/deploy.sh) smoke-tests and restores the previous tag on failure. This only works if
  migrations stay backward compatible.
- **Deploys don't lose jobs.** The worker's SIGTERM release (ADR 0001) and a 70s grace period make restarts safe.

