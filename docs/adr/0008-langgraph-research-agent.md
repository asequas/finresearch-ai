# ADR 0008: An agentic research stage on LangGraph, inside the durable queue

- Status: accepted (2026-10-31)
- Supersedes: the Analyze stage of ADR 0006 (its plan → retrieve → draft chain). ADR 0006's retrieval, verification
  and "the model never does arithmetic" rules all still hold.

## Context

ADR 0006 shipped a fixed chain: plan sub-questions, run one retrieval per sub-question, draft every claim in one
call, judge, write. It works, but it can't do three things an analyst does:

1. **Decide where to look next.** One retrieval per question, chosen before reading anything. A researcher who finds
   a truncated passage reads the rest, and when a search misses, they rephrase.
2. **Work in parallel on independent questions.** Each question is independent until drafting.
3. **Fix its own mistakes.** When the verifier rejected a material claim, the claim was simply dropped. Nobody went
   back to the filings to find the right evidence.

ADR 0006 named the trigger for adopting LangGraph: "when routing becomes dynamic (a planner choosing tools, iterative
research loops)". All three needs are dynamic routing.

Constraints:
- Gemini through a free or cheap tier, so the agent must be budgeted.
- Durability equal to the existing queue: crashes, 429s, cancel and lease loss.
- Every claim still verified by code first.
- Interview-defensible. No agent for its own sake.

## Decision

The deterministic ingestion stages (resolve, fetch, extract, compute, index) are unchanged. What follows them is one
composite stage, `ResearchAgent` (`backend/agent/graph.py`), which runs a LangGraph `StateGraph`:

```
plan ──Send×N──▶ researcher ──▶ draft ──▶ verify ──▶ critic ──▶ synthesize
                  ▲ (tool-using agents, in parallel)       │
                  └────────── Send × gaps (≤ max_revisions) ┘
```

| Node | What it is | Why it is that |
| --- | --- | --- |
| plan | One structured call: 3–6 sub-questions, each with a focus and an approach | Decomposition is reasoning; one call is enough |
| researcher | LangChain `create_agent` with 4 read-only tools, fanned out with `Send` | Choosing searches and reading further is genuinely iterative |
| draft | One strong structured call over the passages the researchers cited, plus their notes and the verifier's feedback | Claim writing needs the whole picture at once |
| verify | ADR 0006's verifier unchanged: verbatim quote check, numbers against metrics, then an LLM judge | Code first; the judge only for what code can't decide |
| critic | **Code, not a model.** Material claims (importance ≥ 2) judged unsupported or partly supported, plus questions whose researcher found nothing, are routed back for one targeted research round. If a revised draft verifies worse than an earlier one, the earlier draft is restored | A routing rule we can state, test and explain beats an LLM deciding whether it's done |
| restore | Re-saves the best earlier draft (kept in graph state with the chunk behind each excerpt id), then goes back to verify | A self-correction loop must be monotonic: revising may only help |
| synthesize | ADR 0006's report writer, recording how the research was done | Unchanged |

**Tools** (`backend/agent/tools.py`):
- `search_filings`: ADR 0007's hybrid search with reranking.
- `read_passage`: the full chunk plus the one after it.
- `get_metrics`: code-computed metrics with their M-handles.
- `get_reported_figures`: XBRL values.

The tools are read-only and stateless. Passages are named by a handle derived from the chunk id (`P:1a2b3c4d`), so a
researcher resumed after a crash sees exactly what the first run saw. A handle the model cites that no tool returned
to it is dropped and recorded (`dropped_handles`), never trusted.

**Budgets**, as hard caps:
- 6 tool calls and 8 model calls per researcher, via `ToolCallLimitMiddleware` and `ModelCallLimitMiddleware`.
- At most 6 researchers.
- 1 revision round.
- 3 researchers at once (`max_concurrency`).

A researcher that runs out of budget still contributes the passages it read.

**Models**:
- Researchers and the chat use `ChatGoogleGenerativeAI`, through `backend/llm/chat.py`. It carries Gemini 3's thought
  signatures across tool turns, falls back through the configured model chain via `ModelFallbackMiddleware`, and
  shares one pacing budget with the structured client.
- Provider errors map onto the queue's types: 429/5xx become `ProviderBusyError`, 401/403 become `PermanentError`.
  The SDK does not retry (`max_retries=0`), because retries belong to the queue, where they are visible.
- The plan, draft, judge and synthesis steps keep the tested `GeminiClient.generate_json`.

### Two checkpoint systems, one owner each

- **The job row** (ADR 0001) owns the job: which worker holds it, its attempts, backoff, cancel and lease fencing.
- **The runner's stage checkpoints** (`agent_runs`) let a retry skip finished ingestion stages.
- **LangGraph's `PostgresSaver`** owns progress inside the agent stage (`thread_id = job id`). On a retry, if the
  saved state has pending nodes, the graph resumes with `invoke(None)` at the node that failed. Writes from parallel
  researchers that finished are kept as pending writes, so a 429 in researcher 5 does not re-run researchers 1–4.
  This is tested.
- The checkpoint is working memory. When the report is written, the thread is deleted; the domain tables are the
  record.

Rules that keep the two systems consistent:

| Rule | Mechanism |
| --- | --- |
| Domain writes are fenced | Every node writes through `ctx.transaction()`, which asserts the lease token first |
| Cancel, lease loss and shutdown are noticed inside the graph | Every node and every tool call starts with `ctx.checkpoint()` |
| Checkpoint writes are *not* fenced | A zombie worker can append at most one checkpoint before its next `ctx.checkpoint()` raises `LeaseLost`. The checkpoint only holds plans and findings (pure functions of the database), and all side effects are fenced, so the worst case is a redone node |
| The checkpoint tables belong to Alembic | Revision `b7e3c91a5d24` contains langgraph-checkpoint-postgres 3.2.0's DDL, frozen; `env.py` keeps autogenerate away from them |

### Ask the analyst

A follow-up chat on a finished report (`backend/services/analyst_chat.py`): one bounded `create_agent` loop per
question, using the same tools plus the report's claims.
- Every quote it cites is checked against its passage (`quote_in_source`, `snap_quote`) and stored as verified or
  not.
- The conversation lives in `report_chat_messages`, the one record. The agent is rebuilt from the last 6 turns, so
  there is no checkpointer for chat.
- The question and answer are committed in one transaction.
- Caps: a busy provider returns 503 with `Retry-After`, and there are 30 questions per report (429).

### Observability

Every node, including each researcher, is an `agent_runs` row with:
- status, attempt, duration and tokens
- metadata: the researcher's question, every tool call with its input, summary and latency, its answer, any dropped
  handles, and the critic's decision and reason

`GET /research/{id}/trace` serves this to the job page's live "Research agent" panel. No new infrastructure was
needed.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep the linear chain | No tool use, no iteration, no self-correction. Kept as `PIPELINE=linear`, a baseline to compare against |
| One ReAct agent writing the whole report | Unbounded context and cost; one long trajectory is hard to resume, test or explain; drafting and verification would no longer be separate steps |
| Deep Agents (`create_deep_agent`) | Planning, a filesystem and subagents come built in, but this workflow's control flow is known: a fixed graph with one bounded loop. The harness would hide the routing an interview asks about |
| LangGraph for ingestion too | Fetching filings and computing metrics have no routing decisions. Wrapping them in nodes adds a second resume mechanism for no behaviour change |
| An LLM critic ("is the report good enough?") | Non-deterministic, costs tokens, and is hard to test. The verifier's verdicts already contain the signal |
| LangSmith tracing | Declined: a third-party data flow and a key for what `agent_runs` already shows in-app |
| A checkpointer for chat | Two copies of the conversation; the chat table is the record |

## Consequences

- More model calls per job: 3–6 researchers × 2–4 calls each, all on the fast model, plus one more draft and judge
  pass when a revision round happens. On Gemini's free tier this hits per-minute quotas sooner. The queue's busy
  backoff and the checkpoint resume make that a delay, not a failure. A paid tier removes it.
- Retrieval is chosen by the researcher, so excerpts are fewer and more targeted; the draft prompt is built only from
  passages a researcher read.
- Four new pinned dependencies (langgraph, langchain, langchain-google-genai, langgraph-checkpoint-postgres), and
  google-genai moved to 2.34.
- Ten user-visible stages instead of eight (plan, research and draft replace analyze).

## Measured on live runs (2026-10-31, Gemini free tier)

| Job | What happened | Final claims | Quotes verbatim | Numbers match |
| --- | --- | --- | --- | --- |
| MSFT | Gemini 503s during research across 3 attempts: each retry resumed the graph and re-ran only the unfinished researcher (q2-q4 ran once). Revision verified worse (10.5 vs 15.5 material claims supported), so the critic restored round 0 | 15 supported, 1 partly | 100% | 100% |
| AAPL (before the restore guard) | All strong models rate-limited at redraft time; the lite fallback dropped every quote and supported claims fell from 17 to 7. This run is why the restore guard exists | 7 supported, 8 unsupported | 0% | 100% |

Two more lessons from these runs became code and tests:
- On a retry, a researcher answered from memory with zero tool calls and seven invented handles. Answers without a
  tool call are now discarded, and the prompt requires a tool first.
- The lite model packed junk into a citation handle (`P:8272934b,quote:`), which marked real quotes unverified.
  Handles are now parsed from the 8 hex digits.

Cost per job: ~110k input and ~9k output tokens (MSFT, including one revision round), 16-21 tool calls.

## Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| 429/503 inside one researcher | `GeminiGuard` maps it to `ProviderBusyError` | Job backs off in minutes; the graph resumes at that researcher only |
| Worker killed mid-graph | Lease expires (ADR 0001) | Next worker resumes from the last checkpoint |
| Researcher loops or wanders | Tool and model call caps | It answers with what it has, or contributes the passages it read |
| Model invents a passage handle | Not in the tool context's `seen` list | Dropped and recorded in the trace |
| Every researcher comes back empty | No handles to resolve | The draft falls back to one plain retrieval of the request |
| Revision doesn't fix a claim | Verdicts after round 1 | Critic stops at the budget; the claim stays flagged in the ledger |
| Revision makes the draft worse (e.g. a weak fallback model) | Critic compares the round's verified material claims with earlier rounds | The better draft is restored and re-verified; the trace shows why |
| Researcher answers without using tools | Empty tool trace | Its findings are discarded; it can't put text into the draft |
| Stale thread after a crash at the very end | Saved state has values but no pending nodes | Thread deleted; graph restarts cleanly |
| Cancel during research | Tool calls check `ctx.checkpoint()` | Stops within one tool call; no report is written |

## When we'd revisit this

- A paid model tier: raise `agent_max_concurrency` and the per-researcher budgets, and consider a second revision
  round.
- A larger eval showing researchers miss evidence the linear retrieval found: add the linear excerpts as a seed for
  the draft.
- Multiple workers per job: today one worker runs a job's graph; parallelism is threads inside it.
- Human review of the plan: `interrupt()` after `plan`, plus an `awaiting_input` job status. The checkpointer already
  supports it.

## Interview questions

1. *"Why LangGraph and not just a loop in Python?"* The workflow has a fan-out with a reducer, a conditional loop
   with a bound, and must resume mid-way after a crash. LangGraph gives those as primitives (`Send`, conditional
   edges, a checkpointer) with tested semantics, such as keeping finished parallel tasks' writes when a sibling fails.
   Hand-rolling durable fan-out/fan-in is where bugs live.
2. *"You already had a durable queue. Why a second checkpointer?"* Different granularity, different owner. The queue
   decides who runs a job and when; the checkpointer remembers where inside the graph we are. The invariant: every
   side effect goes through the lease-fenced transaction, so the unfenced checkpoint can only ever cause a node to be
   redone, never a duplicate or a corrupt write.
3. *"How do you stop an agent from running forever or burning money?"* Hard caps per researcher (tool and model
   calls), a cap on researchers, a bounded revision loop decided by code, and the queue's attempt limit above all of
   it. Budgets are configuration, and the trace shows how much of each was used.
4. *"How do you know the agent isn't hallucinating sources?"* It can only cite handles a tool actually returned (the
   rest are dropped and logged); the draft quotes from those passages; every quote is then checked verbatim in code
   before the LLM judge sees it. The chat applies the same quote check to its answers.
5. *"Why is the critic not an LLM?"* Its decision ("is anything material unsupported, and is there budget left?") is
   fully determined by data we already have. Code makes the loop deterministic, testable and free. Use a model for
   judgement, not for `if` statements.
