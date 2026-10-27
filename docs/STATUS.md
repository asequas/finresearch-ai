# FinResearch AI: Status

Last updated: 2026-10-28 (session 1). Branch `build/end-to-end`.
Labels: **verified** = demonstrated by a test or a command this session; **unverified** = built, not yet demonstrated
against real external services; **proposed** = not built.

## Verified working

| Area | Evidence |
| --- | --- |
| Test suite: 109 tests on an isolated `finresearch_test` database, truncated per test; dev data untouched | `python -m pytest` (dev row counts unchanged before/after) |
| Schema: 5 Alembic revisions, each upgrade → downgrade → upgrade round-tripped; `alembic check` clean with full type comparison (no exemptions) | migration commands on the test DB |
| Durable queue (ADR 0001): exactly one of 10 concurrent claimers wins a job; 5 claimers get 5 distinct jobs; expired leases are reclaimed with a new token; a zombie worker's writes are fenced off | `tests/integration/test_job_queue.py` |
| Crash recovery: a real worker process killed with SIGKILL mid-job is recovered by a second worker after lease expiry; SIGTERM releases the job without spending an attempt | `tests/integration/test_worker.py` |
| Retries with backoff, permanent failures, attempt limits, reaper, cancel (queued and running), user retry, resume from the last completed stage | `test_worker.py`, `test_job_queue.py`, `test_research_api.py` |
| API contract: 202 + Location, Idempotency-Key (same key → same job; different payload → 409; 8 concurrent duplicates → 1 job), ownership-scoped reads (other users' jobs → 404), cursor pagination, filters, input normalisation | `test_research_api.py` |
| Database integrity: CHECK constraints reject bad status, stage, progress and attempts; server defaults work for raw SQL inserts | `test_schema_constraints.py` |
| Metrics engine: 15 metrics in `Decimal`, with formula and inputs; skipped (never guessed) when inputs are missing or denominators aren't positive | `tests/unit/test_metrics.py` |
| XBRL extraction (period-end keyed, restatements, concept fallbacks, provenance), 10-K/10-Q section parsing, chunking, quote and number verification | `tests/unit/` |
| Full research pipeline end to end (8 stages, hybrid retrieval in Postgres, verification, report) with a fake SEC transport and a fake LLM; re-running every stage is idempotent | `tests/integration/test_research_pipeline.py` |
| Report API and Companies API; evaluation metrics and label scoring | `test_research_pipeline.py` |
| Frontend: strict TypeScript build; production bundle; all 7 screens pass the design inspector at 1440/768/390 (0 FAIL); light and dark themes; claim, figure and metric inspectors open with the right content | `npm run build`, `inspect.mjs --app`, playwright-cli screenshots |

## Implemented but unverified

- **Real SEC EDGAR and Gemini calls.** The client code, rate limiting, caching and error classification are tested
  against fakes only. Needs `GEMINI_API_KEY` and `SEC_USER_AGENT` in `.env`, then one real run per stage.
- Gemini model names (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-embedding-001`) are configurable defaults; confirm
  they are available on the free tier for this key.
- 10-K section splitting on real filings (tested on synthetic HTML only); falls back to indexing the whole document.
- Prompt quality: claim density, quote fidelity and synthesis quality are unknown until real runs are labelled.
- Citation correctness ≥ 95%: tooling exists (`backend/evals/citations.py`); no human-labelled set yet.
- Light theme has been checked on the report screen only.

## Known bugs / debt

| # | Severity | Issue |
| --- | --- | --- |
| D1 | Medium | Dev database (`finresearch`) is still at revision `411c859e2482` and holds audit-era test junk (62 test users, 51 queued jobs). Upgrading it fails orphaned `running` rows (the migration says so); the queued junk would then be picked up by a worker. Needs a decision before the first real run. |
| D2 | Low | `StarletteDeprecationWarning` (httpx → httpx2) still present; check `httpx2` provenance before switching. |
| D3 | Low | A heading-only quote (e.g. "Item 1A. Risk Factors") passes the literal quote check; the LLM judge is the only guard against irrelevant-but-verbatim evidence. |
| D4 | Low | Debt uses reported long-term debt only (leases and commercial paper excluded); stated in every report's limitations. |
| D5 | Low | No CI yet; no structured logging beyond stdlib logging. |
| D6 | Low | Development identity: every request is `dev@finresearch.local`. Ownership checks exist; authentication doesn't. |

## Current phase + next 3 tasks

Phases 1–4 and 3b: built and verified with fakes. Phase 5 (RAG + verification): built; evaluation pending real data.
Phase 5b (report reader): built. Phase 6: scope-reduced by decision (no price data). Phase 7 (deploy): deferred by decision.

1. Add the two keys, decide what to do with the dev DB junk (D1), migrate dev to head, run 3–5 real companies. *proposed*
2. Label the claims from those runs and score citation correctness; tune prompts until the target holds. *proposed*
3. CI (GitHub Actions: pytest with a Postgres service, frontend typecheck/build), then deployment design. *proposed*

## Open decisions

- Dev DB junk (D1): delete audit-era test rows, or keep them and cancel them in bulk.
- Whether to merge `build/end-to-end` into `main` after a real-data run.
- Deployment topology and authentication (deferred to the deploy phase).
- Whether to add a price-data source later (licensing; excluded for v1).
