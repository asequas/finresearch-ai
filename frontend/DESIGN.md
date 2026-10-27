# FinResearch UI design system

Direction: **Analyst Terminal**, chosen by Abishek on 2026-10-28. Built with the `data-terminal` app style from the
design-taste-frontend skill (seed 1425590224, dark), with the brand's typeface and accent kept.

## The idea

A research desk you can trust. Every number is in a monospace that stacks in columns, every claim opens to its
source, and colour is spent only on what the user must notice: the job stage running now, the current fiscal year,
and status (supported, partly supported, unsupported, failed).

- **Signature element: the stage strip.** Eight segments, one per pipeline stage. Completed stages are ink, the
  running stage carries the accent, a failed stage the negative colour. It appears on every job row and on the job
  page, so "where is my research" is answered at a glance.
- **The style's one move:** every selection (nav item, tab, filter, theme) is a 1px accent line as wide as its
  label. No filled tabs, no tinted nav rows.
- **Mark:** a filing whose last line is the checked one (`public/mark.svg`, `Mark` in `components/icons.tsx`).

## Tokens (see `src/styles.css`)

| Role | Dark (default) | Light |
| --- | --- | --- |
| ground | `#171719` | `#f4f5f6` |
| surface (cards) | `#131217`, soft shadow, no border | `#ffffff`, 1px `#e3e5e8` border |
| raised / hover | `#212023` | `#f1f2f4` |
| rule (row dividers) | `#1b1a1f` | `#eeeff1` |
| control border | `#3a3a3e` | `#c9cdd3` |
| text / soft / muted | `#ffffff` / `#c9cacd` / `#8a8c92` | `#111316` / `#33363c` / `#5c6068` |
| accent (teal) | `#2bb3a3` | `#0e8a7d` |
| positive / negative / warning | `#44a282` / `#e5566f` / `#e0a84a` | `#247b50` / `#c4242a` / `#92400e` |
| primary button | white fill, near-black label | near-black fill, white label |

Every text tier passes 4.5:1 on its surface. The accent stays under about 3% of pixels.

**Type:** IBM Plex Sans for text (400/500/600), IBM Plex Mono for every figure, ticker, date and ID (tabular).
Sizes: title 26, section figure 20, card title 16/600, reading text 15, body 13, meta 12. Nothing under 11px.

**Shape:** cards radius 6, controls fully round (34px tall), chips 20px tall. Spacing on a 4px base; one 24px gap
between panels; 24px panel padding.

## Rules the screens follow

- Facts, calculations and interpretations are labelled as such on every claim; the inspector sheet explains each type.
- Data freshness, the source filing, claim support counts and limitations are always visible on the report, never only in tooltips.
- Numbers are right-aligned in tables; missing values are a grey dash; real zeros print as `0`.
- Charts: one series each, 3-5 faint gridlines, round ticks above the maximum, no y-axis line, the accent only on
  the current period. Charts draw at their measured width so axis text stays 11px.
- Every view has loading (flat bars at the real size), empty (dashed frame with one sentence), error (in the
  failed block, with Retry) and partial states (stage failures, skipped metrics, unsupported claims).
- Phone: the rail becomes a bottom bar with labels; tables scroll inside their frame; 16px margins.

## Libraries

React 19, React Router 7, TanStack Query 5 (polling while jobs are active), openapi-fetch with types generated from
FastAPI's OpenAPI schema (`npm run api:types`; `npm run api:check` fails if the frontend's copy drifts). No component
or chart library: the few components and the two chart types are small enough to own, which keeps the bundle at
~110 kB gzipped and every visual decision explicit. Fonts are self-hosted via Fontsource.
