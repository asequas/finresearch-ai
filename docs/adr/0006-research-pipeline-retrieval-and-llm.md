# ADR 0006: Research pipeline, retrieval and LLM usage

- Status: accepted (2026-10-28)

## Context

One ticker and question in, an evidence-backed report out, in a few minutes, at near-zero cost (Gemini free tier), on a laptop.

## Decision

**Orchestration: the durable stage runner from ADR 0001, not LangGraph (for now).** The workflow is a fixed sequence of eight stages with one bounded verification pass. The stage runner already gives us persisted progress, per-stage checkpoints, retries, fencing and cancellation; LangGraph's checkpointer would be a second persistence layer to reconcile with the job queue. We'd adopt LangGraph when the workflow gains genuine dynamic routing (the planner choosing tools, iterative research loops, human-in-the-loop review).

| Stage | Deterministic or LLM | Output |
|---|---|---|
| resolving_company | deterministic (SEC ticker map + submissions) | `companies`; financial-sector SIC 6000–6799 → permanent "unsupported in v1" |
| fetching_filings | deterministic | latest 10-K (+ latest 10-Q) in `documents` |
| extracting_financials | deterministic (XBRL companyfacts) | 5 fiscal years in `financial_snapshots` |
| computing_metrics | deterministic, tested formulas | `calculated_metrics` |
| indexing_documents | deterministic parse + Gemini embeddings (768-d) | `document_chunks` (skipped if already indexed) |
| analyzing | LLM (fast model), hybrid retrieval per sub-question | `claims`, `evidence` |
| verifying | deterministic checks first, then LLM judge for the rest | `verification_status` |
| synthesizing | LLM (strong model) over verified claims and metrics only | `reports` |

**Retrieval: hybrid search in Postgres.** Full-text search (`tsvector` generated column + GIN) and pgvector cosine similarity (HNSW), fused with Reciprocal Rank Fusion (k=60), filtered to the job's documents. No reranker until the evaluation shows a need.

**Embeddings:** `gemini-embedding-001` with `output_dimensionality=768`, L2-normalised (required below 3072 dimensions). This matches the existing `vector(768)` column, so no re-embedding migration is needed. `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` task types.

**LLM adapter:** a small `LLMClient` protocol (`generate_json(schema)`, `embed`) with a Gemini implementation and a deterministic fake for tests. Structured output via JSON schema, temperature 0–0.3, token usage recorded per stage in `agent_runs`.

**Verification:** (1) every evidence quote must literally appear (whitespace-normalised) in its chunk; (2) calculation claims must reference a metric and every number in the text must match it within rounding; (3) a fast-model judge rates the remaining fact/interpretation claims against their quotes as supported, partially supported or unsupported. Unsupported claims stay in the evidence ledger, flagged, and are excluded from the executive summary.

**Models (revised 2026-10-28 after the first real run):** `gemini-3.5-flash-lite` for planning and fact-checking,
`gemini-3.6-flash` (a thinking Flash model) for drafting and synthesis. Pro models return 429 on the free tier, so the
"stronger model for synthesis" is a reasoning Flash model. Both are settings, not code.

**Rate limits:** SEC fair access (≤10 requests/s, declared User-Agent) through a process-wide limiter and an on-disk cache; Gemini 429 and 5xx responses raise `RetryableError`, so the queue's backoff handles quota bursts.
The free tier allows 100 embedding requests a minute and counts every text in a batch, so embeddings are paced by a
rolling-window limiter (90/min), chunks are ~2,200 characters, and a 429 during indexing waits out the API's
suggested delay rather than failing the stage. Filings are indexed once and shared by every job that uses them.

## Alternatives

- **LangGraph for the whole pipeline**: see above; adds a second state store without new capability for a linear pipeline.
- **Vector-only retrieval**: misses exact terms (segment names, "goodwill impairment") that keyword search finds.
- **Local embeddings (bge-base, 768-d)**: free and private, but adds torch (~1 GB). Revisit if the Gemini free tier changes.
- **One big "write the report" prompt**: unverifiable and more prone to hallucination; claims-then-verify-then-synthesize keeps each LLM call small and checkable.

## Failure modes

| Failure | Handling |
|---|---|
| SEC down / 429 | RetryableError → queue backoff; the cache avoids refetching |
| Gemini quota exhausted | RetryableError with backoff; after max attempts the job fails with a readable reason |
| Model returns invalid JSON | One repair retry, then RetryableError |
| Filing lacks expected sections | Index what exists; limitation recorded |

## Interview questions

1. *"Why not LangGraph?"* It's a fine tool, but the workflow is linear and the durability already lives in the job queue; two checkpointing systems is a consistency problem. I'd bring it in for dynamic routing.
2. *"Why hybrid retrieval?"* Embeddings capture meaning, BM25-style search captures exact financial terms; RRF combines rankings without score calibration.
3. *"How do you know answers are grounded?"* Literal-quote check, numeric consistency against computed metrics, an LLM judge, and an evaluation set scoring citation correctness.
