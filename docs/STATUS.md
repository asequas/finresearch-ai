# FinResearch AI: Status

Last updated: 2026-10-28 (session 1, after the first real runs).
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

### Real runs (2026-10-28, live SEC EDGAR + Gemini free tier)

| Company | Outcome | Claims | Quotes verbatim | Numbers match metric | Supported / partly / unsupported |
| --- | --- | --- | --- | --- | --- |
| MSFT | completed (re-synthesized after the scenario-basis fix) | 16 | 100% | 100% | 15 / 1 / 0 |
| COST | completed | 16 | 100% | 100% | 12 / 4 / 0 |
| NVDA | completed (late-January fiscal year labelled correctly; newer 10-Q included) | 19 | 100% | 100% | 17 / 2 / 0 |
| JPM | failed on attempt 1, as designed: "financial-sector industry (National Commercial Banks) … not supported" | | | | |

What the real runs proved, beyond the fakes: XBRL extraction on real filings (MSFT FY2022 revenue $198.27B, five
years, no missing fields); recovery from a real embedding quota (429), a schema bug and two Gemini 503 outages via the
queue's retries; graceful SIGTERM release and resume-from-checkpoint on live jobs.

What they broke, now fixed and tested: running page headers truncating 10-K sections (81k vs 4.8k characters);
outdated default model names (Pro has no free-tier quota); embedding quota (100 texts/min) needing pacing; integer
enums rejected by Gemini's schema format; internal C#/M# handles leaking into scenario text.

## Implemented but unverified

- Citation correctness ≥ 95%: automatic metrics are 100% quote verification and numeric consistency on real runs,
  but no human-labelled set yet (`python -m backend.evals.citations export <job_id>`).
- Light theme has been checked on the report screen only.
- Free-tier daily quotas are unknown; each job uses ~150-300 embedding requests (shared filings are indexed once).

## Known bugs / debt

| # | Severity | Issue |
| --- | --- | --- |
| D1 | Low | One intermittent test failure seen once while a live worker shared the machine; it didn't reproduce in 4 reruns. Likely a timing-sensitive worker test under CPU load. |
| D2 | Low | `StarletteDeprecationWarning` (httpx → httpx2) still present; check `httpx2` provenance before switching. |
| D3 | Low | A heading-only quote (e.g. "Item 1A. Risk Factors") passes the literal quote check; the LLM judge is the only guard against irrelevant-but-verbatim evidence. |
| D4 | Low | Debt uses reported long-term debt only (leases and commercial paper excluded); stated in every report's limitations. |
| D5 | Low | No CI yet; no structured logging beyond stdlib logging. |
| D6 | Low | Development identity: every request is `dev@finresearch.local`. Ownership checks exist; authentication doesn't. |

## Current phase + next 3 tasks

Phases 1–4 and 3b: built and verified with fakes. Phase 5 (RAG + verification): built; evaluation pending real data.
Phase 5b (report reader): built. Phase 6: scope-reduced by decision (no price data). Phase 7 (deploy): deferred by decision.

1. Label the claims from the real runs and score citation correctness against the 95% target. *proposed*
2. Tune prompts where the fact-checker flags interpretations as overreaching. *proposed*
3. CI (GitHub Actions: pytest with a Postgres service, frontend typecheck/build), then deployment design. *proposed*

## Open decisions

- Deployment topology and authentication (deferred to the deploy phase).
- Whether to add a price-data source later (licensing; excluded for v1).
