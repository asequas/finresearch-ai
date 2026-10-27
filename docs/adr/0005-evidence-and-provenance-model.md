# ADR 0005: Evidence, provenance and the fact / calculation / interpretation split

- Status: accepted (2026-10-28)

## Context

The product promise is trust: every material claim is either backed by evidence or explicitly marked unsupported, and the reader can tell a **reported fact** from a **calculation** from an **AI interpretation**. Financial numbers must keep their units, period, source filing and retrieval time. Scope (see STATUS): SEC EDGAR only, non-financial companies, no market price data.

## Decision

Data flows through four layers, each persisted and linked to the one before it:

1. **Sources** (`companies`, `documents`): SEC company record (CIK, SIC) and filings (form, accession number, period, filed date, URL, `retrieved_at`). Shared across jobs and deduplicated by `accession_number` / `content_hash`.
2. **Reported facts** (`financial_snapshots`): one row per job × fiscal year with values from SEC XBRL `companyfacts`. `provenance` (JSONB) maps each field to `{concept, accession, filed, form, unit}`, so any number traces back to the exact XBRL fact. Values are `Numeric`, read as `Decimal`. The derived columns (`gross_margin`, `operating_margin`, `free_cash_flow`) are dropped from this table, because derivations are calculations.
3. **Calculations** (`calculated_metrics`): one row per job × metric × period with `value`, `unit`, `formula` (human readable), `inputs` (JSONB naming each input value and its snapshot), and `calculation_version`. Produced by pure Python functions with unit tests (`backend/analysis/metrics.py`). The LLM never does arithmetic; it can only cite metric keys.
4. **Claims** (`claims` + `evidence` + `claim_evidence`): `claim_type ∈ {fact, calculation, interpretation}` (CHECK), plus `section`, `position`, optional `metric_id` (for calculation claims), `verification_status ∈ {supported, partially_supported, unsupported, not_verified}` and a `verification_note`. Evidence rows hold the exact quoted excerpt, the chunk and document it came from, and `quote_verified` (did the excerpt literally occur in the chunk text).

Reports (`reports`) store the synthesized sections as structured JSON, plus `data_as_of` (latest fiscal period end), `limitations`, and the models used.

## Alternatives

- **Free-text report with inline URLs**: cheap, but nothing is checkable and the UI can't separate facts from interpretation.
- **Company-level fact cache instead of per-job snapshots**: saves storage, but a report must stay reproducible after SEC restates numbers. Per-job snapshots freeze exactly what the report used (and are small: ~5 rows per job).
- **Store calculations only as formulas, recompute on read**: reproducibility then depends on the code version at read time; storing value + inputs + version makes the report self-describing.

## Consequences

More tables and joins, but the reader UI gets a direct path from any claim to its source passage or its formula and inputs. Restatements show up as a different accession in provenance.

## Failure modes

- XBRL concept missing for a company (tag differences: `Revenues` vs `RevenueFromContractWithCustomerExcludingAssessedTax`): ordered fallback list per metric; if all are missing, the value is NULL and the metric that needs it is skipped and listed in report limitations, never guessed.
- LLM cites a chunk that doesn't contain the quote: `quote_verified=false`, so the claim can't be `supported`.

## Interview questions

1. *"How do you stop the LLM hallucinating numbers?"* It never produces them. Numbers come from XBRL facts or tested formulas; the model references metric keys, and verification checks that numbers in the claim text match the metric within rounding.
2. *"Why snapshot per job?"* Reproducibility under restatement.
3. *"How do you show provenance for a margin?"* The metric row has the formula and named inputs; each input points to a snapshot field whose provenance names the XBRL concept and filing accession.
