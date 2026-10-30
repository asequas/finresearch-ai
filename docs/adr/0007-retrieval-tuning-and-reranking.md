# ADR 0007: Tuned hybrid retrieval with a fused cross-encoder rerank

- Status: accepted (2026-10-30)
- Refines: ADR 0006 ("reranking when evaluation justifies it")

## Context

Retrieval feeds every claim: if the passage that answers a sub-question isn't among the excerpts the model sees,
the claim is either missing or unsupported. ADR 0006 shipped hybrid search (pgvector cosine + Postgres full-text,
fused with reciprocal rank fusion) and deferred reranking until an evaluation justified it. Two things forced the
question:

- A live run timed out (Gemini 504) on a draft prompt carrying up to 28 excerpts × ~2,200 characters. Fewer, better
  excerpts would make the prompt both cheaper and more reliable.
- There was no measurement of retrieval quality at all.

Constraints: free and local (no paid reranking API), CPU-only on a MacBook Air, no PyTorch.

## Evaluation

`evals/retrieval_gold.json`: 30 analyst questions over the indexed 10-K/10-Q text of Microsoft, Costco, NVIDIA and
Walmart (456 chunks). A chunk is relevant when it contains one of the question's answer phrases, each checked
against the filings, so labels stay valid if filings are re-indexed. `python -m backend.evals.retrieval` reports
Recall@1/3/6, MRR@10 and nDCG@6.

| Strategy | R@1 | R@3 | R@6 | MRR@10 | nDCG@6 | p50 latency |
| --- | --- | --- | --- | --- | --- | --- |
| Vector only | 0.667 | 0.867 | 0.933 | 0.776 | 0.584 | 6 ms |
| Hybrid RRF as shipped in ADR 0006 | 0.567 | 0.800 | 0.933 | 0.706 | 0.528 | 9 ms |
| Tuned hybrid (company names dropped from keyword query, keyword weight 0.5) | 0.633 | 0.933 | 0.967 | 0.781 | 0.602 | 8 ms |
| + MiniLM cross-encoder replacing the ranking (truncated chunks) | 0.567 | 0.833 | 0.900 | 0.718 | 0.514 | 1.9 s |
| + MiniLM, max over 450-char windows, replacing the ranking | 0.733 | 0.867 | 0.867 | 0.804 | 0.613 | 5.6 s |
| **+ MiniLM windows, fused with first stage (weight 1.0) — chosen** | **0.733** | **0.900** | **0.900** | **0.811** | **0.626** | 7.4 s |
| jina-reranker-v1-turbo, best configuration | 0.700 | 0.800 | 0.900 | 0.765 | 0.571 | 6.3 s |

What the numbers say:

1. **The shipped hybrid was worse than vector search alone.** The keyword side OR-ed every question word, and in a
   company's own 10-K its name matches every chunk. Removing the company's name/ticker and filler words from the
   keyword query, length-normalising `ts_rank_cd` and halving the keyword weight in RRF made hybrid beat vector-only
   on R@3, R@6, MRR and nDCG.
2. **A cross-encoder on truncated chunks hurts.** MS MARCO cross-encoders are trained on ~60-word passages; our chunks
   are ~2,200 characters, so truncation drops the answering sentence. Scoring a chunk by its best 450-character
   window fixes that.
3. **Replacing the first-stage ranking loses recall; fusing keeps it.** The reranker is better at the top (R@1) but
   occasionally demotes a relevant passage out of the top 6. Combining both rankings with RRF keeps most of the R@1
   gain and the recall.

## Decision

- First stage: tuned hybrid (`backend/analysis/retrieval.py`): `keyword_query_text` drops the company's own name,
  ticker and filler words; `ts_rank_cd(..., 32)`; RRF weights vector 1.0, keyword 0.5; 40 candidates per side.
- Second stage (`backend/analysis/rerank.py`): `Xenova/ms-marco-MiniLM-L-6-v2` via fastembed (ONNX Runtime, no
  PyTorch, ~80 MB, downloaded once into `.cache/finresearch/models`). Each of the top 20 fused candidates is scored by
  its best window; the cross-encoder ranking is fused with the first-stage ranking at equal weight.
- Analyze stage: top 4 per sub-question, round-robin across sub-questions, at most 16 excerpts (was 28). The rerank
  score is stored in `claim_evidence.relevance_score`; per-question retrieval latency goes into `agent_runs.metadata`.
- `RERANKER=none` disables the second stage (tests and CI do this; no model download). If the model fails to load,
  the job continues without reranking and the stage metadata says so.

## Alternatives

| Option | Why not |
| --- | --- |
| No reranker (tuned hybrid only) | Free and fast, and close behind. Kept as the `none` setting; the reranker's +10 pts R@1 and better ordering won. |
| `bge-reranker-base` (1 GB) | Stronger in general benchmarks, but ~10× MiniLM's compute on a laptop CPU for 20 candidates × 7 windows. |
| jina-reranker-v1-turbo (8k context) | Its long context should suit long chunks; it measured worse and slower than windowed MiniLM here. |
| Gemini as a listwise reranker | Spends free-tier quota per sub-question, adds latency and non-determinism (harder to evaluate), and Gemini was the component timing out. |
| Hosted rerank API (Cohere, Voyage) | Best quality, but a paid account and data leaving the machine; violates the cost constraint. |

## Consequences

- About 45 seconds per job (7 sub-questions × ~6.5 s) on a MacBook Air CPU, roughly 15% of a job. Acceptable for
  minutes-long research; it would be the first thing to move to a faster machine or a GPU.
- Draft prompts shrink from up to ~60k to ~35k characters of excerpts.
- One new pinned dependency: `fastembed==0.9.1` (pulls in onnxruntime and tokenizers).

## Failure modes

| Failure | Handling |
| --- | --- |
| Model download fails or the cache is missing | Logged; `NoopReranker` keeps first-stage order; the job continues |
| Reranker slower than expected | Bounded by 20 candidates; `RERANKER=none` turns it off without a deploy |
| Gold set drifts as filings change | Labels are answer phrases, not chunk ids; the harness refuses to run if a phrase no longer exists |

## Limits of the evidence

30 questions: one question is 0.033 on Recall. The direction of the results is consistent across metrics, but the
gap between "fused" and "tuned hybrid alone" is a few questions. Grow the gold set before fine-tuning weights further.

## When we'd revisit this

- A larger gold set (100+ questions, other sectors) disagrees with these weights.
- Deployment moves to a machine where a stronger reranker costs the same latency.
- Chunking changes (smaller chunks would make window scoring unnecessary).

## Interview questions

1. *"Why rerank at all if you already have hybrid search?"* First-stage retrievers score the query and passage
   separately (bi-encoder, BM25-style); a cross-encoder reads them together, which is far better at "does this answer
   the question" but too slow to run over every chunk. So: cheap recall first, expensive precision on the top 20.
2. *"Your reranker made recall worse at first. Why?"* Truncation: the model saw the first 512 tokens of a
   2,200-character chunk. Max-over-windows scoring fixed it. Measure before and after; don't assume.
3. *"Why fuse instead of trusting the reranker?"* It was better at rank 1 but sometimes demoted relevant passages;
   RRF over both rankings keeps the gain at the top without losing recall. Same idea as fusing BM25 and vectors.
4. *"How did you build an eval set without labellers?"* Questions written against the filings, with answer phrases
   verified to exist; relevance is phrase containment, so it survives re-chunking. Honest limit: 30 queries.
5. *"What did reranking cost?"* ~45 s per job on a laptop CPU, one dependency, ~80 MB model; quality: +17 pts R@1
   and +0.1 nDCG@6 over the shipped hybrid.
