# FinResearch AI: Status

Last updated: 2026-11-01 (recruiter README and demo video).
Labels: **verified** = demonstrated by a test or a command this session; **unverified** = built, not yet demonstrated
against real external services; **proposed** = not built.

## Verified working

| Area | Evidence |
| --- | --- |
| Test suite: 233 tests (plus 1 opt-in model test) on an isolated `finresearch_test` database | `python -m pytest`; `-m model` for the real reranker |
| Research agent (ADR 0008): LangGraph plan → parallel tool-using researchers (`Send`) → draft → verify → code critic → bounded revision → synthesize; Postgres checkpointer inside the durable queue. Tested: fan-out and merge, revision loop bounded, a worse revision restored, resume after a 429 without re-running finished researchers, cancel mid-research, tool-less answers discarded, invented handles dropped | `tests/integration/test_research_agent.py`, `test_agent_tools.py` |
| Agent on live data: MSFT completed through three Gemini 503 attempts, resuming the graph each time (finished researchers not repeated); the revision verified worse and the critic restored the better draft. Final: 15/16 supported, 100% quotes verbatim, 100% numbers match | `python -m backend.evals.citations auto 167fb858-…`; `/research/{id}/trace` |
| Agent self-correction on live data: NVDA's critic sent one unsupported claim and one empty-handed question back; after the revision all 16 claims were supported (100% quotes, 100% numbers), in 4 min 47 s | `/research/cb8b23ad-…/trace` |
| Ask the analyst: tool-using follow-up agent; citations checked against the filing (live: 2 of 2 quotes verified on MSFT); 429 at the turn cap, 503 with Retry-After when the provider is busy, question + answer committed together | `tests/integration/test_analyst_chat.py`, playwright-cli session |
| Fair-value blend (ADR 0012; supersedes the Damodaran FCFF model of ADRs 0010-0011): cash-flow DCF on reported FCF after stock compensation + earnings power value, range where they land, reverse DCF against the price; stock-based compensation added from XBRL (revision `3bc1c688ca22`); all six companies revalued with zero LLM calls (`llm_calls` 111 before and after) | `tests/unit/test_fair_value.py` (hand-worked case), `test_fair_value_defaults.py`, `tests/integration/test_valuation_*.py`, `python -m backend.valuation.backfill --revalue` |
| Delayed price: Cboe quote with no key, cached 15 min, labelled personal/demo; a typed price overrides it; failure degrades to "enter a price"; injected in tests (`PRICE_SOURCE=none`) | `tests/unit/test_valuation_price.py`, `test_valuation_api.py::test_the_delayed_quote…`, playwright at 1440/390 with zero console errors |
| Demo video and README for reviewers: a 2:15 walkthrough recorded from the real app (`docs/demo/finresearch-demo.mp4`) and a highlight GIF; stored report limitations refreshed from code (no model calls; `llm_calls` 111 before and after) | `docs/demo/`, README |
| Cost ledger (ADR 0009): every Gemini response is a priced row (input/cached/output/thinking tokens, dated list price in Decimal, billed vs free tier), attributed to job and stage even inside LangGraph's parallel researcher threads; embeddings counted with countTokens | `tests/integration/test_costs.py`, `tests/unit/test_pricing.py`, `test_research_agent.py::test_every_model_call_lands_in_the_cost_ledger…` |
| Spend caps: $1/day and $5/month on billed calls; new research and chat refused with 429 and the reset time; running jobs stop resumably; free tier never blocks | `tests/integration/test_costs.py` |
| Fewer wasted calls and tokens: a 429 puts the model in cool-down so later calls skip it; old researcher tool results compacted to citable headers; fallback chain limited to priced models | `tests/unit/test_llm_fallback.py`, `tests/unit/test_agent_cost_controls.py` |
| Costs tab (`/costs`): caps with meters, usage by day/model/stage/job, method note; job page shows each job's cost; phone layout without page overflow | playwright-cli at 1440 and 390, zero console errors |
| Agent trace UI (job page) and chat sheet (report) in the browser at 1440 and 390, zero console errors | playwright-cli, `docs/screenshots/agent-trace.png`, `analyst-chat.png` |
| Retrieval quality: tuned hybrid + MiniLM rerank vs the original hybrid on a 30-question gold set: R@1 0.567→0.733, R@3 0.800→0.900, MRR 0.706→0.811, nDCG@6 0.528→0.626 (ADR 0007) | `python -m backend.evals.retrieval` |
| Live browser walkthrough (playwright-cli) at 1440/768/390: submit from the palette, live stages, cancel/retry, report, claim/figure/metric inspectors, keyboard Escape + focus return, filters in the URL, Markdown export, company workspace; zero console errors | demo session 2026-10-30/31 |
| Design gate: 0 FAIL on every route (`inspect.mjs --app`), lint 0 FAIL; Vercel web-interface-guideline findings fixed | automated design inspection, run locally |
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
| D1 | Medium | Gemini free-tier capacity varies a lot by hour (503/504 bursts, 429s on the strong model). The agent multiplies calls (16-21 tool calls, ~110k input tokens per job), so the free tier now delays most jobs: MSFT took 11 minutes over 3 attempts. Jobs ride it out (resume + restore guard). Fix planned: move to a paid Gemini tier, then raise `agent_max_concurrency`. |
| D8 | Low | Fair-value limits (stated in every report): today's capex intensity is treated as permanent, so firms in investment phases (MSFT, AMZN) read low; industry-average betas (10-11% cost of capital for big tech); options and cross-holdings excluded; long-term debt only. All six covered companies currently price in 22%+ annual FCF growth. |
| D9 | Low | Cboe's delayed quote is licensed for personal, non-commercial use only; swap `latest_price` to a licensed feed before any commercial deployment. |
| D7 | Low | The AAPL report from the first agent run predates the restore guard (7/15 supported). Retry it to regenerate. |
| D2 | Low | Reranking costs ~40 s per job on a laptop CPU (7 sub-questions × ~6 s). |
| D3 | Low | Gold set is 30 questions; differences of one question (0.033) are noise. |
| D4 | Low | Debt uses reported long-term debt only; stated in every report's limitations. |
| D5 | Low | No structured logging beyond stdlib. (Per-call cost tracking and caps: done, ADR 0009.) |
| D6 | Low | Development identity: every request is `dev@finresearch.local`. Ownership checks exist; authentication doesn't. |
| D10 | Low | The SSH deploy step (ADR 0013) is *implemented but unverified*: there is no server yet. The image builds on amd64 and arm64, the stack smoke test (a stub research job through nginx) and the GHCR multi-arch publish are verified (CI run 41239201319). |

## Current phase + next 3 tasks

Phases 1–5b: built and verified on real data. Phase 6: fair value + delayed price built; peer comparison deferred. Phase 7 (deploy):
CI/CD built (ADR 0013): images for amd64 and arm64, a smoke-tested stack, GHCR, and an SSH deploy with rollback,
off until a server is configured. Auth deferred by decision.

1. Link billing (Tier 1), set `GEMINI_BILLING=paid`, then tune agent concurrency and budgets against latency; re-run AAPL. *proposed*
2. Human-label claims from the real reports and score citation correctness against the 95% target. *proposed*
3. Deployment design (auth, budgets, rate limits, hosting) through the coach protocol. *proposed*

## Open decisions

- Deployment topology and authentication (deferred to the deploy phase).
- A licensed price feed (needed before any commercial use; would also enable peer multiples).
