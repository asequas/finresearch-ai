# FinResearch AI: Status

Last updated: 2026-10-31 (after the live-demo bug sweep, reranking and the UI pass).
Labels: **verified** = demonstrated by a test or a command this session; **unverified** = built, not yet demonstrated
against real external services; **proposed** = not built.

## Verified working

| Area | Evidence |
| --- | --- |
| Test suite: 138 tests (plus 1 opt-in model test) on an isolated `finresearch_test` database; ran 4× under full CPU load with no failures | `python -m pytest`; `-m model` for the real reranker |
| Retrieval quality: tuned hybrid + MiniLM rerank vs the original hybrid on a 30-question gold set: R@1 0.567→0.733, R@3 0.800→0.900, MRR 0.706→0.811, nDCG@6 0.528→0.626 (ADR 0007) | `python -m backend.evals.retrieval` |
| Live browser walkthrough (playwright-cli) at 1440/768/390: submit from the palette, live stages, cancel/retry, report, claim/figure/metric inspectors, keyboard Escape + focus return, filters in the URL, Markdown export, company workspace; zero console errors | demo session 2026-10-30/31 |
| Design gate: 0 FAIL on every route (`inspect.mjs --app`), lint 0 FAIL; Vercel web-interface-guideline findings fixed | `.taste-skill/inspect2/` |
| One-command start with preflight (`scripts/dev.sh`, `python -m backend.core.preflight`) | stopped DB reported as a sentence |
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
| WMT | completed after the model-chain fix; first reranked report | 20 | 93% | 100% | 15 / 5 / 0 |
| AMZN | completed on attempt 1 from the UI; after the table-row evidence fix | 16 | 100% | 100% | 14 / 1 / 1 |
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

Fixed this round (each found in the live demo or the known list, each with a test): Gemini function-calling warning
spam; heading-only quotes counting as evidence, and then the over-correction that rejected table rows; paraphrased
quotes (now snapped to the filing's wording); provider overloads failing jobs (minute-scale backoff, 5 attempts);
`gemini-flash-latest` hanging 3 minutes per call (removed from the chain; bounded thinking; 90s timeout); Starlette
httpx warning (httpx2); timing-sensitive worker tests; phone overflow on Research; duplicate "Ticker" labels;
misleading cancel copy; quote highlight missing for table rows.

| # | Severity | Issue |
| --- | --- | --- |
| D1 | Medium | Gemini free-tier capacity varies a lot by hour (503/504 bursts). Jobs now ride it out, but a burst can stretch a 4-minute job to 10+. Report quality drops when the draft falls back to a lite model (quotes still verified, so weaker claims are flagged, not hidden). |
| D2 | Low | Reranking costs ~40 s per job on a laptop CPU (7 sub-questions × ~6 s). |
| D3 | Low | Gold set is 30 questions; differences of one question (0.033) are noise. |
| D4 | Low | Debt uses reported long-term debt only; stated in every report's limitations. |
| D5 | Low | No structured logging beyond stdlib; no per-job cost budget. |
| D6 | Low | Development identity: every request is `dev@finresearch.local`. Ownership checks exist; authentication doesn't. |

## Current phase + next 3 tasks

Phases 1–5b: built and verified on real data. Phase 6: scope-reduced by decision (no price data). Phase 7 (deploy):
CI added; deployment and auth deferred by decision.

1. Human-label claims from the six real reports and score citation correctness against the 95% target. *proposed*
2. Grow the retrieval gold set to 100+ questions across more sectors before tuning weights further. *proposed*
3. Deployment design (auth, budgets, rate limits, hosting) through the coach protocol. *proposed*

## Open decisions

- Deployment topology and authentication (deferred to the deploy phase).
- Whether to add a price-data source later (licensing; excluded for v1).
