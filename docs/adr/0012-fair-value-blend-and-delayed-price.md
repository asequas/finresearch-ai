# ADR 0012: Fair-value blend (cash-flow DCF + earnings power) and a free delayed price

- Status: accepted (2026-11-01)
- Supersedes: ADR 0010 and ADR 0011. The stage, storage, what-if API, cited metrics and the Treasury rate stay; the
  model changes.

## Context

ADR 0011 made the Damodaran FCFF model agree better with prices. It got there through judgement calls:
- capitalised R&D with industry lives
- a 10-year horizon for "wide-advantage" firms
- excess returns that fade but never end, capped at 25%

The user asked whether those numbers could be trusted. They wanted something "more reliable and stable in our
case". They also wanted the current price fetched automatically, at no cost and with no API key.

Constraints are unchanged:
- deterministic, Decimal, reproducible from stored inputs
- no model calls
- free data only
- every input sourced

## Decision

### 1. Three simple methods, all built from reported numbers (`backend/valuation/fair_value.py`, `fv-2.0`)

| Method | Formula | Why |
| --- | --- | --- |
| **Cash-flow DCF** | Free cash flow = cash from operations + after-tax interest − capex − stock-based compensation, per year from SEC XBRL. The base is the 3-year average FCF *margin* × the latest revenue. Growth = revenue CAGR over the years held, clamped to [0, 20%], for 5 years; then a linear fade over 5 years to 2.5% long-run growth (never above the risk-free rate). Terminal: Gordon growth. | Uses cash the company actually produced. The margin average smooths lumpy years without dragging a fast grower back to old revenue. |
| **Earnings power value** (Greenwald) | Average operating margin × latest revenue × (1 − tax) ÷ cost of capital | No growth at all: a floor that ignores forecasts entirely |
| **Reverse DCF** | Bisection on the first years' growth (0–60%) until the DCF equals the price | Turns a price into a statement the reader can judge: "the price needs X% a year; the record is Y%" |

- **Fair value** = the mean of the methods that apply.
- **Range** = from the lowest method to the highest.
- A method that doesn't apply drops out with a stated reason: FCF ≤ 0 removes the DCF, and operating losses remove
  earnings power.
- Kept from ADR 0010:
  - cost of capital via CAPM with Damodaran's industry unlevered beta, relevered at the industry D/E
  - Treasury 10-year as the risk-free rate
  - Damodaran's implied ERP
  - synthetic-rating default spread
  - the equity bridge (cash + short-term investments − debt − minority interest)
- Stock-based compensation is a new XBRL fact (`ShareBasedCompensation`), added in Alembic revision `3bc1c688ca22`
  and backfilled from SEC companyfacts.

### 2. Price: Cboe's delayed quote, labelled personal/demo (`backend/valuation/price.py`)

- Source: `cdn-api.cboe.com/api/global/delayed_quotes/quotes/{SYMBOL}.json`. No key, about 15 minutes delayed,
  cached 15 minutes per symbol under the data cache.
- Fetched when a valuation is read, never stored with the report. The written report still makes no price claims.
- A failed fetch means no price, never an error. `PRICE_SOURCE=none` turns it off; tests run that way.
- **Licensing:** Cboe's site terms allow personal, non-commercial use. The UI labels the quote
  "personal/demo use". A paying product needs a licensed feed (Polygon, IEX Cloud successors, the exchange's own
  licence) behind the same `latest_price` function.
- A price the reader types always overrides the quote.

### 3. Price check (`backend/services/valuation.py: price_check`)

- Position: below, within or above the fair-value range. The UI calls these "looks undervalued", "roughly fairly
  valued" and "looks overvalued".
- Gap: fair value ÷ price − 1.
- Implied growth from the reverse DCF, compared with **the revenue record**, even inside a what-if, so an edited
  assumption is never presented as the record.
- Shown with a "decision support, not investment advice" line. There is no buy/sell label.

## Effect (stored filings, zero model calls; delayed quotes 2026-10-30)

| | Price | ADR 0011 | Fair value (range) | Price implies | Revenue record |
| --- | --- | --- | --- | --- | --- |
| MSFT | $522.99 | $742 | $207.80 ($166–249) | 28.2% | 13.7% |
| NVDA | $205.25 | $250 | $70.62 ($33–108) | 32.8% | 68.3% (capped at 20%) |
| AMZN | $240.80 | $175 | $38.06 ($22–54) | above 60% | 11.1% |
| COST | $1,011.20 | $494 | $368.98 ($268–470) | 22.2% | 7.5% |
| WMT | $123.59 | $50 | $31.70 ($30–34) | 27.8% | 5.6% |
| AAPL | $345.10 | $107 | $75.13 ($66–85) | 29.6% | 3.3% |

All six price in much faster cash-flow growth than their records. Two checks show this isn't a modelling slip:
- Raising long-run growth all the way to the risk-free rate (4.94%) only lifts values to 35–50% of the price.
- WMT and COST trade near 70× and 60× free cash flow, so no standard cost of capital gets close.

ADR 0011's higher MSFT and NVDA values came almost entirely from its judgement calls:
- capitalised R&D made reinvestment look productive
- 10 years of high growth
- permanent excess returns

The swing from $742 to $208 is the measure of how much those calls carried.

Known reasons the blend reads low for some firms (shown to the reader, not tuned away):
- **Investment-heavy years.** MSFT's capex rose from $24B to $116B in four years, so its FCF margin fell from 30% to
  17%. The DCF treats today's capex intensity as permanent.
- **AMZN** has had negative FCF years, so its average FCF margin is thin.
- **Industry betas** of 1.25–1.5 put the cost of capital for the tech names at 10–11%.

## Alternatives

| Option | Why not (for now) |
| --- | --- |
| Keep ADR 0011's Damodaran FCFF with R&D and advantage defaults | Accurate to the book, but the result hinged on judgement calls the user didn't trust; less stable year to year |
| Relative valuation (P/E, EV/EBITDA against peers) | Needs peer prices and consistent peer sets; worth adding as a cross-check once a licensed feed exists |
| Analyst-consensus growth | Paid data |
| Dividend discount model | Most of these firms return cash through buybacks; FCF captures that |
| Lower the cost of capital or raise long-run growth until values meet prices | That makes the model a restatement of the market. The reverse DCF already says what the market assumes |
| Yahoo chart API, Nasdaq API, Stooq | Yahoo's terms forbid deriving income; Nasdaq's is undocumented; Stooq blocks scripts. Cboe is documented as free delayed data |
| A paid quote API (Polygon, Alpha Vantage premium) | The user chose free for now; it's a one-function swap later |

## Consequences

- Fewer knobs, and every one is sourced and editable: growth, years, fade, long-run growth, ERP and debt weight.
- Values are conservative for firms in heavy investment phases. The FCF table makes the reason visible.
- One more outbound call when a valuation is opened, cached for 15 minutes; failure degrades to "enter a price".
- `val_*` metrics replace `dcf_*`:
  - `val_fair_value`, `val_dcf_value`, `val_epv_value`, `val_cost_of_capital`, `val_growth`
  - the drafter may cite them as estimates, never against a price
- The company page shows "Fair value per share"; the API field stays `value_per_share`, so the contract is
  unchanged.

## Failure modes

| Failure | Detection | Handling |
| --- | --- | --- |
| Cboe unreachable, symbol unknown, or schema change | `latest_price` returns None (parse errors caught) | No price; "enter a price" form; valuation still shown |
| Stale quote | `as_of` from Cboe's last trade time | Shown next to the price |
| FCF ≤ 0 or operating losses | Method guard | That method drops out with a note; both out means skipped with the reason |
| A what-if that breaks the model (g ≥ WACC or g > Rf) | `InvalidAssumptions` | 400 with the reason |
| Price far outside the model (AMZN) | Bisection finds no root in 0–60% | "No growth rate between 0% and 60% makes the cash-flow DCF match this price" |
| Cboe terms change or we go commercial | Review | Swap `latest_price` to a licensed feed; set `PRICE_SOURCE` |

## When we'd revisit this

- A licensed price feed: add relative valuation against peers, and market-value weights in the cost of capital.
- Separate maintenance from growth capex (e.g. capex ≈ D&A at steady state) for firms in investment phases. This
  needs reinvestment tied to growth, which brings back part of ADR 0011.
- Sector models: banks and insurers (excess returns on equity) remain out of scope.

## Interview questions

1. *"Why three simple methods instead of one rigorous model?"* Each answers a different question: what the cash
   record is worth with growth (DCF), what today's profit is worth with none (EPV), and what the price assumes
   (reverse DCF). Where they agree is a range the reader can trust. A single elaborate model hides its judgement
   calls inside one number.
2. *"Your model says every mega cap is overvalued. Is it broken?"* I checked: raising long-run growth to the
   risk-free rate gets only to 35–50% of the price, and WMT trades at ~70× FCF. The tool's job is to state what
   the price requires (28% a year for MSFT against a 13.7% record), not to agree with the market.
3. *"How do you get prices with no budget?"* Cboe publishes free delayed quotes without a key. Its terms are
   personal and non-commercial, so the UI labels it, caches it, degrades to a typed price, and isolates it behind
   one function so a licensed feed is a config change.
4. *"Why deduct stock-based compensation?"* It's a real cost paid in shares instead of cash. Adding it back
   overstates owner cash flow by $12B a year at Microsoft.
5. *"Why average margins rather than dollars?"* A dollar average of a company that grew 4× undervalues it at
   today's scale. The margin average keeps the smoothing and applies it to current revenue.
