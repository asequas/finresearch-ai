# ADR 0011: Valuation v2: capitalised R&D, advantage-aware defaults, and a price check

- Status: superseded by ADR 0012 (2026-11-01)
- Refines: ADR 0010 (the DCF engine is unchanged; calculation version `dcf-1.1`)

## Context

Customers want to judge whether a stock looks undervalued or overvalued. The first DCF defaults put every company
far below its market price:
- MSFT −19%
- NVDA −43%
- AMZN −53%
- COST −63%
- WMT −69%
- AAPL −77%

Re-running the stored inputs one assumption at a time found three causes:
1. **R&D was treated as an expense.** Apple's capex roughly equals its depreciation, so it showed about 1%
   reinvestment and 1.8% growth while spending about $35B a year on R&D. Damodaran capitalises R&D.
2. **Every company got 5 high-growth years.** That fits average firms, not firms earning several times their cost
   of capital.
3. **Stable return on capital = cost of capital.** "No excess returns forever" made all stable growth value-neutral.
   Damodaran relaxes this for firms with sustained advantages.

The product also had no way to set an estimate against a price. A price feed was declined (unofficial sources,
licensing), so the comparison has to work without one.

## Decision

1. **Capitalise R&D** when it is at least 1% of revenue (`research_asset` in `backend/valuation/dcf.py`).
   - Each year's R&D is amortised straight-line over an industry life: 3 years for software and services, 5 for
     hardware and semiconductors, 10 for pharma and aerospace.
   - Operating income adds back R&D − amortisation, and reinvestment counts the same amount. The unamortised
     research asset joins invested capital, so return on capital is measured on it too.
   - Years before our data are assumed equal to the earliest reported year, and the valuation notes it.
2. **Advantage-aware defaults** (`backend/valuation/assumptions.py`), each stated in the assumption's source and
   editable in the what-if:
   - 10 high-growth years instead of 5 when return on capital beats the cost of capital by ≥ 10 points.
   - Stable return on capital = midway between the firm's return on capital and its stable cost of capital, capped
     at 25%: the advantage fades but persists. Firms earning below their cost of capital keep ROC = cost of capital.
3. **Price check.** `market_price` on `POST /valuation/what-if`; the reader types the price and the app fetches
   none.
   - The response says whether the price is below, within or above the estimate range, and the gap.
   - It also gives the **growth the price implies**: a reverse DCF that solves for the high-growth rate making value
     equal to price, by bisection, with everything else as assumed.
   - The UI labels the result "looks undervalued / roughly fair / looks overvalued" and always shows implied against
     assumed growth, plus a line that this is decision support, not advice.
   - The research agent still never compares the DCF with a price.

## Effect (same inputs, no model calls; prices from 2026-10-30)

| | Price | v1 | v2 (range) | Price implies | Assumed |
| --- | --- | --- | --- | --- | --- |
| MSFT | $522 | $421 | $742 ($638–888) | 13.4% | 17.9% |
| NVDA | $205 | $117 | $250 ($219–293) | 17.6% | 20.0% |
| AMZN | $240 | $113 | $175 ($153–205) | 15.8% | 11.6% |
| COST | ~$970 | $364 | $494 ($440–568) | 15.5% | 6.8% |
| WMT | $124 | $38 | $50 ($44–59) | 19.3% | 7.0% |
| AAPL | $345 | $79 | $107 ($97–121) | 17.8% | 3.3% |

The remaining gaps are the point of the tool, not a defect. The prices of Walmart, Costco and Apple require 15–19%
annual operating-income growth for a decade, against 3–7% from their reinvestment record. The customer sees that
contrast directly and can test it in the what-if.

## Alternatives

| Option | Why not |
| --- | --- |
| Tune defaults until values match prices | That would make the DCF a restatement of the market, with no information in it |
| A revenue-and-margin DCF (sales-to-capital) instead of fundamental growth | A bigger model change; better for young or loss-making firms. Revisit with a price feed and more history |
| A price feed (Stooq, Alpha Vantage) | Declined: unofficial or quota-limited, unclear licence. The typed price gives the comparison without it |
| A buy/sell label | Overstates certainty and turns decision support into advice; the range, gap and implied growth say more |

## Consequences and limits

- Values depend more on judgement calls (10 years, a 25% cap). They are explicit, sourced, editable, and covered by
  tests.
- R&D before our 5-year history is approximated, which slightly misstates amortisation for long-life (10-year)
  industries.
- The estimate range is narrow (±0.5 points of cost of capital and stable growth). The what-if and implied growth
  carry the real uncertainty.

## Interview questions

1. *"Your DCF said everything was overvalued. What did you do?"* I decomposed the gap by changing one assumption at
   a time. Three defaults (R&D expensed, a 5-year horizon for everyone, no excess returns forever) explained most of
   it. I fixed them the way Damodaran does, and refused to tune values towards the price.
2. *"How do you tell a customer whether a stock is cheap without a price feed?"* They type the price. We place it
   against the estimate range and solve for the growth the price implies, a reverse DCF, which is a more honest
   message than a point estimate.
3. *"Why capitalise R&D?"* It creates long-lived assets the way capex does. Expensing it understates reinvestment
   and invested capital, so growth and return on capital come out wrong for tech and pharma.
