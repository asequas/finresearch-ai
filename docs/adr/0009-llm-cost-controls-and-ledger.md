# ADR 0009: LLM spend: a per-call cost ledger, hard caps, and fewer wasted tokens

- Status: accepted (2026-10-31)
- Builds on: ADR 0006 (LLM adapter), ADR 0008 (research agent)

## Context

The research agent (ADR 0008) makes far more model calls than the linear pipeline, and on Gemini's free tier that
shows up as 429s and 503s. Measured on two live agent jobs:

| | MSFT | NVDA |
| --- | --- | --- |
| Input / output tokens | ~110k / 9k | ~203k / 11k |
| Share of input spent in researcher loops | 79% | 89% |
| Calls to the strong models that succeeded | 0 of 19 (all 429) | 0 |

Two findings drove the design:
1. **Researchers re-send every earlier tool result on every turn**, so input grows quadratically with tool calls.
2. **The fallback chain spent a round trip on models that were certain to refuse.** On the free tier the strong
   models answered nothing, so every strong call cost a 429 before falling back. Worse, the AAPL redraft fell back
   to the weakest model (ADR 0008's restore guard handles the consequence).

The user's goal: the least money, without losing quality, with spend visible in the product. A paid tier is
acceptable with a cap of **$5 a month and $1 a day**.

Prices, from [Google's price list](https://ai.google.dev/gemini-api/docs/pricing), checked 2026-10-31, per 1M tokens:

| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| `gemini-3.5-flash-lite` | $0.30 | $0.03 | $2.50 |
| `gemini-3.6-flash` | $0.75 ($1.50 from 2027-01-01) | $0.075 | $3.75 ($7.50) |

At those prices a job costs about $0.04–0.11.

## Decision

### 1. Spend fewer tokens and requests (free, no quality loss)

- **Compact old tool results** (`backend/agent/context.py`). Before each researcher or chat model call, every
  search/read result except the latest two is reduced to its passage headers (handle, filing, period, section)
  plus the first ~160 characters.
  - The handles stay citable, and `read_passage` brings any of them back in full.
  - Only what is sent changes; the agent's state, and the full passages the drafter receives from the database,
    are untouched.
  - We rejected plain clearing (`ClearToolUsesEdit`) because it erases the handles researchers must cite.
- **Cool-downs** (`backend/llm/pacing.py`). A 429 puts that model in cool-down for Google's suggested `retryDelay`
  (60s if none is given), and a 5xx for 20s. Both clients skip cooling models, so the next call goes straight to a
  model that can answer.
  - The tool-calling model raises `ModelCoolingDown` without a network call, and the fallback middleware moves on.
  - If every model is cooling, the one that recovers first is tried.
- **Optional per-model RPM ceilings** (`GEMINI_MODEL_RPM`), off by default: limits differ per project and are only
  visible in AI Studio.
- **Priced models only** in the fallback chain: `3.6-flash → 3.8-flash → 3.5-flash-lite`. `3.5-flash` and
  `3.7-flash` are dropped: they aren't on the price list, and `3.5-flash` is reported at twice `3.6-flash`'s price.

### 2. A cost ledger (`llm_calls`, migration `c05a71455e15`)

One row per model response, written by the two clients themselves, so nothing billed can be missed. That
includes fallback models, drafts that fail schema validation, researcher turns, chat answers and embeddings.

| Column | Why |
| --- | --- |
| `input_tokens`, `cached_tokens`, `output_tokens`, `thinking_tokens` | Billing classes. Thinking is billed as output; implicitly cached input is billed at the cached rate |
| `cost_usd` (Numeric 14,8) | The list price at the rate in force that day (prices are dated: 3.6-flash doubles on 2027-01-01). NULL if the model isn't on the price list, never a guess |
| `billable` | Whether the project was on a paid tier at the time. Free-tier calls cost nothing; the ledger keeps both "billed" and "list price" |
| `estimated` | Token counts were estimated: rows backfilled from old stage totals, or an embedding batch whose count call failed |
| `research_job_id` (SET NULL), `source`, `stage` | Attribution: job/chat, and which stage or node |

Rules that keep the ledger accurate:

| Rule | Mechanism |
| --- | --- |
| Attribution follows the work | A `ContextVar` set by the stage runner, the agent's node wrapper and the chat service. Tested through LangGraph's parallel researcher threads |
| Embeddings are counted, not guessed | Embedding responses carry no token counts, so each batch is counted with the free `countTokens` endpoint; ~4 characters per token is the flagged fallback |
| Not lease-fenced | A zombie worker's call was still billed |
| Recording never fails a job | Errors are logged instead |
| History without fabrication | `python -m backend.costs.backfill` turns old per-stage token totals into rows flagged `estimated` and not billed |

### 3. Hard caps

`budget_status` sums *billed* rows for the current UTC day and month.
- **New research and chat:** refused with 429 and a sentence saying when the budget resets.
- **Running jobs:** every model call checks first and raises `BudgetExceeded`. The job fails with that message; its
  checkpoint is kept, so Retry after the reset resumes it.
- **Overshoot:** at most one call's worth past the cap, a few cents.
- **Free tier:** never blocks, because nothing is billed.

### 4. The Costs tab (`/costs`, `GET /api/v1/costs`)

- Today and this month against the caps, with meters and reset times.
- Usage value for 7, 30 or 90 days, and the average cost of a completed job.
- Daily spend chart.
- Spend by model (input, cached and output tokens) and by stage.
- The 25 latest jobs with their cost.
- How the numbers are calculated, with counts of estimated and unpriced rows.
- The job page's agent panel shows that job's cost.

## Measured after the change (live COST job, free tier, 2026-10-31)

| | NVDA (before) | MSFT (before) | COST (after) |
| --- | --- | --- | --- |
| Attempts / wall time | 2 / 4 min 47 s | 3 / 11 min | **1 / 3 min 34 s** |
| 429 + 5xx responses during the job | many | 19 + 12 | **2** (the first strong call; later calls skipped the cooling models) |
| Researchers / tool calls | 7 / 25 | 6 / 16 | 6 / 24 |
| Researcher input per tool call | ~7.2k tokens | ~5.4k | **~4.4k** (of which 17% served from Gemini's implicit cache) |
| Job cost at list price (ledger) | ~$0.087 | ~$0.056 | **$0.058** (49 calls, 133k in / 9k out) |
| Quotes verbatim / numbers match | 100% / 100% | 100% / 100% | 100% / 100% (16 of 17 claims supported) |

These are different companies and questions, so the comparison is indicative rather than a controlled A/B. The
cool-down effect is direct: two rejected requests instead of one per strong call.

## Alternatives

| Option | Why not |
| --- | --- |
| Stay on the free tier only | Strong models were never available; jobs took 5–11 minutes through quota errors, and weaker drafts were the result |
| Several free projects to multiply quota | Deliberately gets around Google's limits; terms-of-service risk on a public portfolio project |
| Batch API (half price) | Results within 24 hours; research is interactive |
| A second provider in the fallback chain | New dependency, different tool-calling behaviour and less consistent quality; revisit if Gemini's paid tier isn't enough |
| A local model (Ollama) | ~200k tokens per job through a laptop CPU or GPU is far too slow |
| Budget alerts in Google Cloud only | Alerts notify, they don't stop spending; the in-app cap does, and it's testable |
| Estimating cost from `agent_runs` totals | Per-stage totals miss failed-parse retries, chat and embeddings, and can't split cached input |
| Explicit context caching | The large repeated content (tool results) differs per researcher; implicit caching already prices repeat prefixes at the cached rate, and the ledger records it |

## Consequences

- Per-job cost is visible and capped. At the measured ~$0.04–0.11 per job, $5 a month covers 50–100 jobs.
- One more table and one row per call, about 30–40 rows per job.
- Embedding batches cost one extra (free) `countTokens` request.
- Prices live in code (`backend/costs/pricing.py`). A price change is a one-line, dated entry, and the page shows
  the date the prices were checked.

## Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Google changes a price | Dated price table; page shows the check date | Add a dated entry; old calls keep their old price |
| A model not on the price list gets used | `cost_usd` NULL; counted as "unpriced" on the page | Add its price |
| Cap reached mid-job | `BudgetExceeded` before the next call | Job fails with the reset time; Retry resumes from the checkpoint |
| Ledger write fails | Logged | The job continues; that call's cost is missing |
| `countTokens` fails for an embedding batch | Exception caught | ~4 characters per token, row flagged `estimated` |
| A model stays rate-limited | Cool-down renewed on each 429 | Calls skip it; when the whole chain is cooling, the job backs off (ADR 0001) |

## When we'd revisit this

- Spend approaches the cap regularly: tune researcher budgets first (6 tool calls each), then the cap.
- Multiple users: per-user budgets (the ledger already has the job, and the job has the user).
- A second provider: the ledger's `model` column and price table already generalise.

## Interview questions

1. *"How do you know what the AI costs?"* Every response is a ledger row with its token classes, priced at the
   dated list price in `Decimal`. Recording sits inside the clients, so retries, fallbacks, failed parses and
   embeddings can't be missed, and attribution follows the work into worker threads via a context variable.
2. *"How do you stop runaway spend?"* Hard caps checked before every model call and every submission, counted from
   billed ledger rows. A job that hits the cap stops with a resumable error, never silently. Alerts alone don't stop
   spend.
3. *"Where did the tokens go, and how did you cut them?"* Measurement showed 79–89% of input in researcher loops,
   from re-sending old tool results. Compacting them to citable headers keeps quality (handles survive, and full
   text is one `read_passage` away) and removes the quadratic growth.
4. *"Why did 429s waste time even with fallbacks?"* Each call tried a model that was certain to refuse. A
   cool-down per model, driven by Google's `retryDelay`, turns that into a skip.
5. *"Why record list price on the free tier?"* So the switch to paid has no surprises: the tracker already shows
   what the same usage will bill.
