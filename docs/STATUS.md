# FinResearch AI: Status

Last updated: 2026-10-28 (session 1, forensic audit). Labels: **verified** = reproduced by a command this session; **unverified** = believed true from reading code, not reproduced; **proposed** = not built.

## Verified working

| Area | Evidence (command, 2026-10-28) |
|---|---|
| Python 3.12.6 in `.venv` | `python --version` |
| Postgres 17.11 + pgvector 0.8.6 in container `finresearch-postgres` (healthy) | `docker compose ps`, `select extname, extversion from pg_extension` |
| Migration `411c859e2482` is current and the only head | `alembic current`, `alembic heads` |
| `alembic check`: "No new upgrade operations detected." | `alembic check` (but see debt D6: one column's type comparison is suppressed) |
| Test suite: 14 passed, 1 warning (`StarletteDeprecationWarning`: httpx → httpx2) | `python -m pytest -v` |
| Phase 1 committed (`967c5a2`) | `git log` |
| Phase 2 committed across `b4e3ee3`, `9082ea7`, `afbbeed` (2026-08-30/31); working tree had no uncommitted Phase 2 work | `git status`, `git log` |
| No secrets in git history; `.env` never tracked; `.env` and `.env.example` hold the same single key (`DATABASE_URL`) | `git log --all -- .env`, history grep |
| `POST /api/v1/research` → 201 + job (`queued`, progress 0); `GET /api/v1/research/{id}` → 200 / 404; literal `""` query → 422 | API tests |
| Job creation persists (service commits after repository flush) | API + service tests |
| Service rejects illegal transitions (e.g. completed → running) | service tests |

## Implemented but unverified

- Cascade/`SET NULL` delete rules across all 10 app tables: defined in the migration, never exercised by a test.
- `documents`, `document_chunks` (`vector(768)`), `evidence`, `claims`, `claim_evidence`, `financial_snapshots`, `reports`, `agent_runs`: tables exist; no code reads or writes them.
- Dev-user dependency is unsafe under concurrency (two first requests at once → unique violation → 500). Read from code, not reproduced.
- Tests are not parallel-safe (shared dev DB, shared `dev@finresearch.local` user, module-level `TestClient`). Read from code; `pytest-xdist` not installed, not tried.

## Known bugs / debt (ranked; "verified" = reproduced with a probe script on 2026-10-28)

| # | Severity | Issue | Status |
|---|---|---|---|
| D1 | High | `ResearchJobService.update_status` / `update_progress` never commit. A caller that closes the session loses the change silently (same class of bug as the original flush-vs-commit). Tests hide it by calling `session.commit()` themselves. `backend/services/research_job.py:43-96` | verified |
| D2 | High | State transitions are check-then-write in Python with no lock or conditional UPDATE. Two concurrent workers both moved the same job `queued → running`. | verified |
| D3 | High | Tests run against the dev database and never clean up. One run added 10 users + 12 jobs; DB now holds 62 `@example.com` users and leftover `running`/`completed` jobs. Blocks reliable stale-job and concurrency tests. | verified |
| D4 | Medium | `started_at`, `completed_at`, `error_message` are never set by any code path. All 68 jobs have NULL timestamps, including 6 `completed`. | verified |
| D5 | Medium | No DB integrity for state: `status` is `VARCHAR(32)` with no CHECK (DB accepted `'banana'`; ORM read then raises `LookupError`); `current_stage` is a plain string (DB accepted `'not_a_stage'`; response model then fails, so GET would 500); no CHECK on `progress`. | verified |
| D6 | Medium | `database/migrations/env.py:75-80` suppresses type comparison for `research_jobs.status`. Without it, `alembic check` reports `VARCHAR(32)` vs `Enum(...)` drift. | verified |
| D7 | Medium | Validation gaps: whitespace-only query accepted; ticker not trimmed/uppercased (`' aapl '` accepted); no max length on `query` (100k chars accepted). | verified |
| D8 | Medium | No ownership check on GET; GET doesn't depend on the current user at all. Harmless with one dev user; must exist before auth. | verified (by reading) |
| D9 | Medium | Dev-user dependency commits inside a FastAPI dependency (violates service-owned transactions) and races on first creation. `backend/api/dependencies.py:21-34` | unverified (race), verified (commit location) |
| D10 | Medium | `requirements.txt` is unpinned and lists unused heavy deps (streamlit, celery, redis, langgraph, langchain, google-genai, pandas, numpy, pypdf); `pyproject.toml` declares no dependencies; no lockfile. 110 packages installed. | verified |
| D11 | Low | Response omits `created_at`, `started_at`, `completed_at`, `error_message`; the frontend can't show "failed because…". | verified |
| D12 | Low | No `server_default` anywhere; all defaults are Python-side, so raw-SQL inserts fail NOT NULL and timestamps come from the app clock. | verified (by reading) |
| D13 | Low | Money/ratio columns are `Numeric` in the DB but annotated `Mapped[float]` in models (values are `Decimal` at runtime). | verified (by reading) |
| D14 | Low | Index gaps for later phases: no index on `claim_evidence.evidence_id`; no uniqueness on `financial_snapshots (research_job_id, ticker, period)` (retries can duplicate); `ix_claims_verification_status` low value; no vector index (correctly deferred). | proposed fixes |
| D15 | Low | Dead duplicate `get_db` in `backend/core/database.py:21-27` (API uses `backend/api/dependencies.py:10`). | verified |
| D16 | Low | `alembic` offline mode is broken (`sqlalchemy.url` is blank); `set_main_option` would break on a `%` in the DB password. | verified (by reading) |
| D17 | Low | `docs/ARCHITECTURE.md` (tracked) is stale and contradicts the project brief: "frozen" Streamlit + Celery/Redis + Gemini embeddings, "don't hard-code vector dimension", claims POST returns 202. | verified |
| D18 | Low | Empty tracked scaffolding: `workers/tasks.py`, `workflows/research_graph.py`, `docker/Dockerfile.{api,worker,streamlit}`, `README.md`; empty dirs `agents/*`, `frontend/streamlit`, `tests/unit`, `tests/e2e`, `config`, `scripts`. | verified |
| D19 | Low | Starlette 1.6.0 prefers `httpx2` and falls back to `httpx` 0.28.1 with a warning. Harmless today; check `httpx2` provenance/compatibility before switching. | verified (warning), unverified (`httpx2`) |

## Current phase + next 3 tasks

Phase 1 and 2: implemented and committed, with debt D1–D11. Phase 3 (reliable background execution): **not started**; `workers/tasks.py` is empty.

1. Phase 3 design discussion (coach protocol) → ADRs for execution mechanism, job state machine, and submission idempotency/contract. *proposed*
2. Isolate tests in a dedicated `finresearch_test` database with per-test cleanup (fixes D3). *proposed*
3. Make the service layer own every commit and set lifecycle fields (fixes D1, D4), with regression tests that don't commit on the service's behalf. *proposed*

Full Phase 3 task list: see the session-1 audit; it moves here once agreed.

## Open decisions

- Execution mechanism for Phase 3 (Celery+Redis vs Postgres-backed queue vs other), including DB↔queue consistency. Owner: Abishek's design proposal first.
- Job state machine: retries, attempt limits, stale-job detection, cancellation, timeouts.
- Submission contract: `201` → `202`, idempotency key.
- Enum storage: native PG enum vs `VARCHAR` + CHECK (affects D5/D6 migration).
- Test DB strategy: separate database vs transaction-rollback fixtures vs both.
- Dependency management: pin via lockfile (pip-tools/uv) and prune unused deps.
- Whether to delete or rewrite `docs/ARCHITECTURE.md`.
- Proposed scope cuts from the vision (news API, sector coverage, DCF, peers): awaiting Abishek's call.
