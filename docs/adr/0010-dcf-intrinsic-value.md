# ADR 0010: Deterministic DCF intrinsic value (Damodaran FCFF), no AI in the math

- Status: accepted (2026-10-31)
- Builds on: ADR 0005 (evidence and metrics), ADR 0006 (verification), ADR 0008 (agent), ADR 0009 (costs)

## Context

Readers want an intrinsic value per share for each company they research. The method is Damodaran's,
*Damodaran on Valuation* (2nd ed.), ch. 2 "Intrinsic Valuation":
- free cash flow to the firm (FCFF), discounted at the cost of capital
- a terminal value whose stable growth is capped
- a bridge from firm value to value per share

Constraints:
- **Deterministic.** Decimal, unit-tested formulas, reproducible from stored inputs. Valuation is arithmetic plus
  stated assumptions; an LLM choosing numbers would be neither reproducible nor auditable.
- **No new spend.** Gemini is billed now, so the feature makes no model calls.
- **No market price.** User decision: intrinsic value only, no "undervalued by X%". The weights in the cost of
  capital therefore can't come from market values.
- **Free, attributable data only.**

## Decision

A new deterministic pipeline stage, `valuing` (`backend/pipeline/research.py: Valuate`), runs after metrics and
before indexing. It computes a default valuation from the job's stored snapshots and stores it, with every input
and its source, in `valuations`. Its headline numbers become `dcf_*` metrics, so the existing drafter can cite
them and the existing verifier checks them; `USD/share` is matched to the cent. A what-if API recomputes from the
*stored* inputs and saves nothing.

### Model (`backend/valuation/dcf.py`, version `dcf-1.0`)

| Piece | Formula / rule | Source |
| --- | --- | --- |
| Base cash flow | EBIT × (1 − effective tax); effective = income tax ÷ pre-tax income, capped at the marginal rate | SEC XBRL (new facts: D&A, tax, pre-tax income) |
| Reinvestment | (capex − D&A) + Δ non-cash working capital, aggregated over up to 3 years | SEC XBRL |
| Growth | reinvestment rate × return on capital, clamped to [0, 20%]; falls back to revenue CAGR if the firm is shrinking capital | ch. 2 "fundamental growth" |
| Reinvestment going forward | growth ÷ return on capital, so higher growth must be paid for | ch. 2 |
| Phases | 5 high-growth years, then a 5-year linear fade of growth, reinvestment, cost of capital and tax to stable | Damodaran's three-stage FCFF |
| Cost of capital | E/V × (Rf + β_L × ERP) + D/V × (Rf + default spread)(1 − 25%) | see the data table below |
| Beta | industry unlevered beta (cash-corrected), relevered at the industry D/E; stable β = 1 | his recommended bottom-up beta (a regression beta needs prices) |
| Terminal | g ≤ Rf (default 3%); stable ROC = stable cost of capital (no excess returns), so reinvestment = g ÷ ROC | ch. 2 constraints |
| Bridge | operating value + cash + short-term investments − debt − minority interest, ÷ diluted shares | SEC XBRL |
| Guards | skip with the reason when EBIT ≤ 0 or shares are missing; reject g > Rf and g ≥ cost of capital | |

**Operating leases.** Under ASC 842, operating lease cost is already inside operating income. Subtracting the lease
liabilities as debt as well would double-count them. We found exactly that on Amazon (an $89B lease liability) and
fixed it. Leases stay an operating cost and are left out of the bridge and of invested capital. Treating them as
debt is valid only if EBIT is also adjusted, which is a later option.

### Data, all free and dated

| Input | Source | As of |
| --- | --- | --- |
| Risk-free rate | US Treasury 10-year par yield, from the daily CSV (no key), cached per day; a failed fetch uses the stale cache, and with no rate at all the valuation is skipped | daily |
| ERP | Damodaran's implied ERP for the S&P 500 (4.20%) | 2026-10-01 |
| Industry unlevered beta, D/E | Damodaran US `betas.xls`, vendored as CSV with attribution | 2026-01-05 |
| Default spreads | Damodaran `ratings.xls` (large and small firm tables; firm size by revenue ≥ $5B, because we have no market cap) | Jan 2026 |
| SIC → industry | Our own table (Damodaran publishes none). Narrowest range wins; unmapped codes fall back to the market without financials, flagged | |

## Verification

- **Golden test.** The engine reproduces the chapter's 3M valuation: operating assets $64,020M against $64,036M,
  and **$86.92 against $86.95 a share**. The gap is the book's rounding (44.4%, and a year-5 EBIT of $5,147M).
- **Tests** cover:
  - beta relevering and the cost of capital, by hand
  - the coverage → rating → spread table
  - growth from fundamentals and its fallback
  - fading over the transition years
  - the model constraints and the sensitivity grid
  - the pipeline stage: valued, skipped and idempotent
  - the API: ownership, bounds, and what-ifs leaving the stored valuation unchanged
- **Backfill.** Six existing companies were valued with `llm_calls` unchanged (111 before, 111 after).

## Alternatives

| Option | Why not |
| --- | --- |
| Free cash flow to equity, or a dividend discount model | FCFF is the chapter's main model, is independent of leverage changes, and works for low-payout firms |
| Valuation multiples (P/E, EV/EBITDA) | That's relative valuation and needs prices and peers; out of scope |
| Regression beta | Needs price history (no price data) and is noisy; Damodaran prefers bottom-up betas anyway |
| Market-value weights | Needs a share price; industry averages are his recommended target mix |
| The LLM choosing growth or cost of capital | Not reproducible, not auditable, costs money; assumptions come from code with sources, and the what-if lets a human change them |
| Adding a free price feed (Stooq) | Unofficial, unclear licence; declined by the user |

## Consequences

- Every report carries an auditable intrinsic value with its range, or a stated reason why there isn't one.
- The agent's report can cite the DCF; claims about it are verified against the computed numbers.
- One more stage (milliseconds) and a daily Treasury fetch. The Damodaran data needs a yearly refresh, documented
  in `backend/valuation/data/README.md`.
- **Known model limits, stated in every report's limitations:**
  - R&D is expensed, not capitalised, so R&D-heavy firms look like low reinvesters (Apple's growth comes out at
    1.8%).
  - Options and cross-holdings are not subtracted or added.
  - Diluted weighted shares are used.
  - Long-term debt only.

## Failure modes

| Failure | Detection | Handling |
| --- | --- | --- |
| treasury.gov unreachable | Fetch error | Stale cached rate, marked in the valuation's notes; none cached means skipped |
| Operating loss or missing shares | Guard in `default_inputs` | Stored as skipped with the reason; the report says "No DCF value: …" |
| Implausible fundamental growth (NVDA: 98.9%) | Clamp | Capped at 20%, with a note |
| A what-if that breaks the model (g > Rf) | `InvalidAssumptions` | 400 with the reason |
| Industry not mapped | Fallback flag | Market-wide beta and debt ratio, with a note |
| Damodaran data goes stale | Dated constants shown in every source | Yearly refresh |

## When we'd revisit this

- If a licensed price source is added: market-value weights, margin of safety, and a regression beta to
  cross-check.
- R&D capitalisation (Damodaran's adjustment) for tech and pharma.
- Lease capitalisation with an EBIT adjustment, for retailers and airlines.
- Banks and insurers need an equity (FCFE / excess-return) model. They are out of v1 scope already.

## Interview questions

1. *"Why isn't the valuation done by the LLM?"* It's arithmetic on stated assumptions. Code makes it reproducible,
   testable against a published example (3M, to the cent within rounding) and free. The model's job is to explain
   it, and the verifier checks every number it quotes.
2. *"How do you get a beta without prices?"* Bottom-up: an industry unlevered beta relevered at the industry debt
   ratio. Damodaran argues it beats a noisy regression beta even when prices exist.
3. *"Why doesn't higher stable growth raise the value much?"* With stable return on capital equal to the cost of
   capital, growth has to be fully paid for by reinvestment, so it creates no value. That's the chapter's
   no-excess-returns constraint, and the sensitivity table shows it.
4. *"What did you get wrong at first?"* Subtracting operating lease liabilities as debt while lease cost was
   already in operating income: a double count worth $89B at Amazon. Under ASC 842, model leases consistently on
   one side only.
5. *"How is it reproducible?"* Every input is stored with its source and date (filing facts, Treasury yield,
   Damodaran's data versions, defaults), the calculation is versioned, and what-ifs start from the stored inputs,
   not today's data.
