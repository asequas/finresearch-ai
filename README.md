# FinResearch AI

[![CI](https://github.com/asequas/finresearch-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/asequas/finresearch-ai/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-agents-1C3C3C)
![PostgreSQL 17 + pgvector](https://img.shields.io/badge/PostgreSQL_17-pgvector-4169E1?logo=postgresql&logoColor=white)
![React + TypeScript](https://img.shields.io/badge/React_19-TypeScript-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-amd64_%7C_arm64-2496ED?logo=docker&logoColor=white)

**An AI equity research analyst whose every claim you can check.**

Ask a question about any US-listed company, such as *"How durable is Microsoft's growth, and what are the main risks
to its margins?"* A few minutes later you get a structured research report:
- the direct answer first, then the summary, financials, scenarios and risks
- an **intrinsic valuation** set against today's share price
- an **evidence ledger** in which every claim opens to the exact 10-K passage, figure or formula behind it

A team of LangGraph agents does the reading. Deterministic code does every calculation. A verifier checks each claim
before it reaches you, and anything that can't be verified is flagged, not hidden.

![FinResearch demo: claim evidence, a code-computed metric, fair value, the agent trace and the cost ledger](docs/demo/demo.gif)

**▶ Full 2-minute walkthrough**, recorded on the real app with real reports on Microsoft's 10-K (no live model calls
during the recording):

https://github.com/user-attachments/assets/052b5d0a-8247-49fb-98fd-71ef3b0956cc

## What it does

| Capability | What you get |
| --- | --- |
| 🔎 **Research** | Type a ticker and a question. The job runs in the background; leave and come back, and it survives restarts and crashes. Live stage-by-stage progress shows what the system is doing. |
| 🤖 **Agent team** | A planner splits your question into 3–6 sub-questions. Parallel researcher agents search the 10-K and 10-Q, read passages and pull metrics, and a fact-checker sends weak claims back for another look. |
| 🧾 **Evidence** | Each claim is typed as a **reported fact** (quoted verbatim from the filing), a **calculation** (formula, inputs and XBRL source shown) or an **interpretation** (labelled as opinion), with a verdict: supported, partly supported or unsupported. |
| 📈 **Financials** | Revenue, margins, free cash flow, growth, ROE and leverage from SEC XBRL. Every figure carries its filing, period and concept, and is computed in `Decimal` by tested code, never by the model. |
| 💲 **Valuation** | A fair value per share from two methods (a cash-flow DCF and earnings power value). It is set against a free delayed share price, and a **reverse DCF** tells you how much growth the price assumes, next to the company's actual record. A what-if panel lets you change any assumption. [More below](#intrinsic-valuation). |
| 💬 **Analyst chat** | Follow-up questions answered by a tool-using agent that searches the same filings; its quotes are checked against the source too. |
| 🧮 **Costs** | Every model call is priced into a cost ledger, with daily and monthly caps. A full report costs about **$0.04–0.11**. |
| 📄 **Reports** | Saved reports with data freshness, sources and limitations; export to Markdown or print to PDF; works on a phone. |

## Product tour

| | |
| --- | --- |
| ![Overview](docs/screenshots/overview.png) | ![Live job](docs/screenshots/job-live.png) |
| **Overview.** What's running and what's ready; ⌘K searches every company, report and job. | **Live job.** Eleven checkpointed stages with typical durations; leave and come back any time. |
| ![Research agent](docs/screenshots/agent-trace.png) | ![Ask the analyst](docs/screenshots/analyst-chat.png) |
| **Research agent.** The plan, every researcher's tool calls, and the fact-checker's decisions. Here it sent a failed claim and an empty-handed question back for another round, and all 16 claims ended up supported. | **Ask the analyst.** Follow-up questions answered by a tool-using agent; each cited quote is checked against the filing. |
| ![Report](docs/screenshots/report.png) | ![Claim inspector](docs/screenshots/claim-inspector.png) |
| **Report.** The answer first, then summary, financials, scenarios, risks and the evidence ledger. | **Claim inspector.** Every claim opens to the filing passage with the quoted words highlighted. |
| ![Company workspace](docs/screenshots/company.png) | ![Phone](docs/screenshots/phone-report.png) |
| **Company workspace.** Five years of reported figures and every report on the company. | **Phone.** The same report, laid out for a small screen. |
| ![Costs](docs/screenshots/costs.png) | ![Valuation](docs/screenshots/valuation.png) |
| **Costs.** Every model call priced from its token counts, against daily and monthly caps; by day, model, stage and job. | **Valuation.** Fair value from a cash-flow DCF and earnings power, every assumption sourced; the delayed price is placed against the range, with the growth it implies. |

## Results at a glance

| | Result | Evidence |
| --- | --- | --- |
| **Trustworthy output** | Fresh run on Alphabet: 15 claims, 14 supported, 1 partly, 0 unsupported; 100% of quotes verbatim in the filing and 100% of numbers matching code-computed metrics, in ~3 minutes for $0.08. NVIDIA: the agent's critic sent a failed claim back and all 16 ended up supported | [`docs/STATUS.md`](docs/STATUS.md), `python -m backend.evals.citations auto <job>` |
| **Better retrieval, measured** | Recall@1 0.567 → **0.733** and MRR 0.706 → **0.811** on a 30-question gold set over real filings, after tuning hybrid search and adding a local cross-encoder | [ADR 0007](docs/adr/0007-retrieval-tuning-and-reranking.md), `python -m backend.evals.retrieval` |
| **Survives failure** | A worker killed with `kill -9` mid-job is recovered by another; the Microsoft run rode out three provider outages by resuming from its Postgres checkpoint without redoing finished work | `tests/integration/test_worker.py`, [ADR 0001](docs/adr/0001-postgres-backed-job-queue.md) |
| **Cheap to run** | **~$0.04–0.11 of model spend per report**, every call priced in a ledger with hard daily and monthly caps; CI/CD on free runners; a ₹0 hosting plan | [ADR 0009](docs/adr/0009-llm-cost-controls-and-ledger.md), [Cost engineering](#cost-engineering) |
| **Tested and shipped like production** | 233 tests on a real Postgres; CI builds x86 and ARM images, boots the whole stack and runs a research job through it before anything is published | [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [ADR 0013](docs/adr/0013-ci-cd-and-single-host-deploy.md) |
| **Decisions written down** | 13 architecture decision records, each with alternatives, failure modes and when to revisit | [`docs/adr/`](docs/adr) |

## Intrinsic valuation

Most "AI analyst" tools ask a language model what a stock is worth. FinResearch computes it: in code, from the
company's own reported numbers, with every assumption sourced and editable.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/valuation-dark.png">
  <img alt="Valuation method: SEC XBRL, Treasury and industry inputs feed a CAPM cost of capital, a cash-flow DCF and earnings power value; the fair value and range are checked against a delayed share price with a reverse DCF" src="docs/diagrams/valuation-light.png">
</picture>

**How it works**
- **Cash-flow DCF.** Free cash flow is what the business actually produced: cash from operations plus after-tax
  interest, minus capex and stock-based compensation. The base is the 3-year average FCF margin applied to the latest
  revenue. Growth starts at the company's revenue record (capped at 20%) for five years, then fades to 2.5% forever.
- **Earnings power value.** Today's normalised operating profit after tax, divided by the cost of capital. This
  assumes no growth at all, so it is a floor that ignores forecasts entirely.
- **Cost of capital.** CAPM with Damodaran's industry beta relevered at the industry debt ratio, the Treasury 10-year
  yield as the risk-free rate, and a synthetic-rating default spread for debt.
- **Fair value** is the midpoint of the methods, and the **range** is where they land.
- **Price check.** The share price comes from Cboe's free delayed quote, or you can type one. A reverse DCF solves for
  the growth rate that would justify that price. The verdict reads "looks undervalued", "roughly fairly valued" or
  "looks overvalued", always with the implied growth next to the company's record, so you can judge the gap yourself.
- **What-if.** Change the growth rate, the number of years at that growth, the fade, long-run growth, the equity risk
  premium or the debt ratio. The server recomputes from the stored inputs, saves nothing and calls no AI. A
  sensitivity grid shows how far the value moves.

**On the covered companies** (fair values from filings; delayed quotes of 2026-11-02):

| Company | Fair value (range) | Share price | Growth the price needs | Revenue record | Cost of capital |
| --- | --- | ---: | ---: | ---: | ---: |
| Microsoft (MSFT) | $207.80 ($166–249) | $527.77 | 28.3% / yr | 13.7% | 10.06% |
| Alphabet (GOOGL) | $99.14 ($88–110) | $285.58 | 30.9% / yr | 11.8% | 10.06% |
| Apple (AAPL) | $75.13 ($66–85) | $340.78 | 29.3% / yr | 3.3% | 10.40% |
| NVIDIA (NVDA) | $70.62 ($33–108) | $209.24 | 33.2% / yr | 68.3% (capped at 20%) | 11.20% |
| Costco (COST) | $368.98 ($268–470) | $1,022.94 | 22.4% / yr | 7.5% | 8.09% |
| Walmart (WMT) | $31.70 ($30–34) | $125.22 | 28.1% / yr | 5.6% | 8.09% |
| Amazon (AMZN) | $38.06 ($22–54) | $252.98 | above 60% / yr | 11.1% | 8.09% |

All seven trade well above what their reported cash flows support at a standard cost of capital. That isn't a bug,
and the defaults were deliberately not tuned toward the price. The point of the reverse DCF is to say exactly how much
growth the market is paying for. Microsoft needs about 28% a year against a 13.7% record; whether that's reasonable
is the investor's call. The model's known blind spot is shown in every report: firms in a heavy investment phase
(Microsoft's capex went from $24B to $116B in four years) read low, because today's capex intensity is treated as
permanent. The full reasoning is in [ADR 0012](docs/adr/0012-fair-value-blend-and-delayed-price.md). The report
itself cites the fair value as an estimate and never makes price claims; the comparison lives in the valuation view.

> Decision support, not investment advice. The quote source is licensed for personal, non-commercial use.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/system-dark.png">
  <img alt="System architecture: React UI and nginx in front of a FastAPI service; PostgreSQL with pgvector holds the job queue, filings and chunks, the claim-evidence ledger, metrics and valuations, agent checkpoints and the cost ledger; workers run the ingestion stages and the LangGraph agent and call SEC EDGAR, Gemini, a local reranker, the US Treasury and Cboe; CI builds, smoke-tests and deploys" src="docs/diagrams/system-light.png">
</picture>

- **PostgreSQL does the heavy lifting.** It is the job queue (`FOR UPDATE SKIP LOCKED` claims, leases, fencing
  tokens), the vector store (HNSW `vector(768)` with `tsvector` for hybrid search), the evidence ledger, the agent's
  checkpoint store and the cost ledger. Submitting a job and enqueueing it is one transaction, so nothing can be lost
  between a database and a broker.
- **Workers scale horizontally.** Each claims a job, heartbeats its lease and writes only while it still holds the
  lease. A crashed worker's job is picked up by another and resumed at the last completed stage.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/pipeline-dark.png">
  <img alt="One research job: six deterministic ingestion stages, then a LangGraph agent that plans, fans out parallel researcher agents, drafts, verifies with code and an LLM, and uses a code critic to send material failures back once before writing the report" src="docs/diagrams/pipeline-light.png">
</picture>

<details>
<summary><b>Every stage in detail</b></summary>

| Stage | Kind | Output |
| --- | --- | --- |
| Resolve company | deterministic | SEC CIK, industry (financial-sector companies are rejected in v1) |
| Fetch filings | deterministic | latest 10-K and any newer 10-Q |
| Extract financials | deterministic | five fiscal years from XBRL, latest filing wins on restatement |
| Compute metrics | deterministic | margins, FCF, growth, ROE, leverage, CAGR, each with formula and inputs |
| Fair value | deterministic | cash-flow DCF + earnings power value; industry beta, Treasury 10-year, Damodaran ERP; range, sensitivity |
| Index filings | deterministic + embeddings | section-aware chunks, `tsvector` + HNSW `vector(768)` |
| Plan | LLM | 3-6 sub-questions, each with a focus |
| Research | parallel tool-using agents | each researcher searches (tuned hybrid + local cross-encoder rerank), reads passages and pulls metrics, within a call budget |
| Draft | LLM | claims citing only passages the researchers read, plus verifier feedback on a revision |
| Verify | code first, then LLM; code-routed revision | quote check, numeric check, fact-check verdicts; material failures go back to a researcher once |
| Synthesize | LLM | answer, summary, bull/base/bear with anchored assumptions, risks, limitations |

</details>

## Engineering highlights

### Skills demonstrated

| Area | What's in this repo | Where |
| --- | --- | --- |
| Backend and API design | FastAPI + Pydantic; `202 Accepted` + `Location` + `Idempotency-Key` (8 concurrent duplicates → 1 job); cursor pagination; ownership-scoped reads; a strict router → service → repository layering where only services own transactions | [`backend/api`](backend/api), [`backend/services`](backend/services), [ADR 0003](docs/adr/0003-submission-contract-and-idempotency.md) |
| Distributed systems | A durable job queue on Postgres: `FOR UPDATE SKIP LOCKED` claims, leases with heartbeats, fencing tokens against zombie workers, retries with backoff, a reaper, cancellation, resume from the last completed stage | [`backend/worker`](backend/worker), [ADR 0001](docs/adr/0001-postgres-backed-job-queue.md), [ADR 0002](docs/adr/0002-job-state-machine.md) |
| Agentic AI | LangGraph `StateGraph` with `Send` fan-out to parallel tool-using researchers, reducers, a code-routed critic with one bounded revision, a guard that restores the better draft, and a Postgres checkpointer inside the queue's lease | [`backend/agent`](backend/agent), [ADR 0008](docs/adr/0008-langgraph-research-agent.md) |
| RAG and evaluation | Section-aware chunking; `tsvector` + HNSW `vector(768)` hybrid search fused with reciprocal rank fusion; a local MiniLM cross-encoder; a labelled gold set with recall, MRR and nDCG | [`backend/analysis`](backend/analysis), [`backend/evals`](backend/evals), [ADR 0007](docs/adr/0007-retrieval-tuning-and-reranking.md) |
| Hallucination control | Every claim typed as fact, calculation or interpretation; quotes matched verbatim in code, numbers matched against computed metrics, then an LLM fact-check; unsupported claims stay visible and out of the summary | [ADR 0005](docs/adr/0005-evidence-and-provenance-model.md), [ADR 0006](docs/adr/0006-research-pipeline-retrieval-and-llm.md) |
| Data and financial engineering | SEC EDGAR client with fair-access rate limiting and caching; XBRL extraction with provenance (concept, accession, period, filed date); `Decimal` metrics with unit-tested formulas; a cash-flow DCF, earnings power value and reverse DCF with a CAPM cost of capital | [`backend/sources`](backend/sources), [`backend/analysis/metrics.py`](backend/analysis/metrics.py), [`backend/valuation`](backend/valuation), [ADR 0012](docs/adr/0012-fair-value-blend-and-delayed-price.md) |
| Databases | PostgreSQL 17 schema with constraints doing real work (unique idempotency keys, check constraints, cascades); Alembic migrations round-tripped and drift-checked in CI | [`database/migrations`](database/migrations), [ADR 0004](docs/adr/0004-enum-storage.md) |
| Frontend | React 19 + TypeScript, TanStack Query, a client typed from FastAPI's OpenAPI schema (`npm run api:check` fails on drift); live job progress, claim inspector, what-if valuation; keyboard-navigable, responsive, with designed loading, empty, error and partial states | [`frontend/`](frontend), [`frontend/DESIGN.md`](frontend/DESIGN.md) |
| Testing | 233 tests: ten threads racing for one job, a real `kill -9` of a worker, SIGTERM release, the full pipeline against a fake SEC and a scripted tool-calling model; no test can reach a paid API | [`tests/`](tests) |
| DevOps | Multi-stage Docker images, nginx, Compose; a GitHub Actions matrix on native amd64 and arm64 runners; GHCR; an SSH deploy that migrates, smoke-tests and rolls back automatically | [`.github/workflows`](.github/workflows), [`deploy/`](deploy), [ADR 0013](docs/adr/0013-ci-cd-and-single-host-deploy.md) |
| Observability | A trace of every agent and tool call rendered live on the job page; a priced row per model call; stage timings per job | [`backend/costs`](backend/costs), [ADR 0009](docs/adr/0009-llm-cost-controls-and-ledger.md) |

### Why it's production grade

- **No lost or duplicated work.** Submitting a job and enqueueing it is one Postgres transaction, so there's no dual
  write to a broker. Delivery is at-least-once; exactly-once *effects* come from fencing tokens, idempotent stage
  writes and unique constraints. HTTP retries with the same `Idempotency-Key` return the same job.
- **Crashes are routine, not incidents.** Leases expire and another worker takes over; SIGTERM releases a job without
  burning a retry; a retried job resumes at the LangGraph node that failed. All of it is tested with real processes.
- **Correctness before cleverness.** The model never does arithmetic. Deterministic work (fetching filings, parsing
  XBRL, metrics, valuation) is plain tested code; LLMs are used only for planning, research, drafting and judging.
- **Failures are visible.** Missing data, skipped metrics, unsupported claims and the report's limitations are shown,
  not hidden. Financial-sector companies are rejected up front with a reason.
- **Safe delivery.** Every change runs the tests, a migration drift check and a full-stack smoke test on
  both CPU architectures. Deploys migrate before traffic and roll back on a failed health check.
- **Guard rails on spend.** Daily and monthly caps refuse new work with a clear 429 once spent; running jobs stop at a
  resumable point instead of failing.

### Cost engineering

Cost was a design constraint from the start: free or local where quality allows, paid only where it earns its keep,
and every cent measured.

| Decision | Effect |
| --- | --- |
| Deterministic code for everything that doesn't need judgement (ingestion, metrics, valuation, quote and number checks) | Most of the pipeline makes no model calls at all |
| Cheap model for routine steps, a stronger one only for synthesis and judging; fallbacks limited to priced models | Spend goes where reasoning quality matters |
| Old tool results compacted to citable headers before each researcher call | Input per tool call 7.2k → 4.4k tokens; job cost $0.087 → $0.058 |
| A 429 puts that model in cool-down for the provider's suggested delay | Later calls skip it instead of being rejected again |
| Resume from the LangGraph checkpoint after a failure | Finished researchers are never re-run, so retries don't double the bill |
| Local cross-encoder reranker (ONNX, on CPU) | Better retrieval with no per-query API cost |
| On-disk caches: SEC filings (immutable), Treasury yield (daily), delayed quotes (15 min) | Re-runs and re-reads are free |
| A per-call cost ledger at dated list prices, with $1/day and $5/month caps | ~$0.04–0.11 per report, and spend can't run away |
| Tests can't reach the paid API (blocked at the client) | CI and local runs cost nothing |
| Postgres as the queue, vector store and checkpointer | One stateful service instead of Postgres + Redis + a vector DB |
| GitHub Actions and GHCR on a public repo; a single Docker host (Oracle Cloud's free Arm VM fits) | CI/CD and a hosting plan at ₹0 |

### Design decisions

Each significant decision is an ADR with the alternatives considered, failure modes and when to revisit it:
[durable queue on Postgres](docs/adr/0001-postgres-backed-job-queue.md) ·
[job state machine](docs/adr/0002-job-state-machine.md) ·
[202 + idempotency keys](docs/adr/0003-submission-contract-and-idempotency.md) ·
[enum storage](docs/adr/0004-enum-storage.md) ·
[evidence and provenance model](docs/adr/0005-evidence-and-provenance-model.md) ·
[pipeline, retrieval and LLM use](docs/adr/0006-research-pipeline-retrieval-and-llm.md) ·
[retrieval tuning and reranking](docs/adr/0007-retrieval-tuning-and-reranking.md) ·
[LangGraph research agent](docs/adr/0008-langgraph-research-agent.md) ·
[LLM cost controls and ledger](docs/adr/0009-llm-cost-controls-and-ledger.md) ·
[DCF intrinsic value](docs/adr/0010-dcf-intrinsic-value.md) ·
[valuation v2: R&D, advantage, price check](docs/adr/0011-valuation-v2-rd-advantage-price-check.md) ·
[fair-value blend and delayed price](docs/adr/0012-fair-value-blend-and-delayed-price.md) ·
[CI/CD and single-host deploy](docs/adr/0013-ci-cd-and-single-host-deploy.md).

## Run it locally

Requirements: Python 3.12, Node 22+, Docker.

Once set up (below), one command starts the database, migrations, API, a worker and the UI, and explains anything
that's missing:

```bash
scripts/dev.sh        # UI on http://localhost:5173
```

First-time setup:

```bash
# 1. Database
docker compose up -d                                   # Postgres 17 + pgvector

# 2. Backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env                                   # then fill in the values below
alembic upgrade head
uvicorn backend.main:app --reload                      # API on :8000, docs at /docs

# 3. Worker (one or more, in other terminals)
python -m backend.worker.main

# 4. Frontend
cd frontend && npm install && npm run dev              # UI on :5173
```

`.env`:

```bash
DATABASE_URL=postgresql+psycopg://finresearch:<password>@localhost:5432/finresearch
GEMINI_API_KEY=<free key from https://aistudio.google.com/apikey>
SEC_USER_AGENT=FinResearch AI <your contact email>       # SEC EDGAR requires a contact address
# PIPELINE=stub                                          # run the queue with fake stages, no external calls
```

## Deploy

CI builds the production images for x86 and ARM, boots the full stack from them, and runs a research job through
nginx before anything ships. On `main` the tested images go to GHCR, and the Deploy workflow ships them to one
server over SSH: migrate, restart, smoke test, automatic rollback ([ADR 0013](docs/adr/0013-ci-cd-and-single-host-deploy.md)).

On the server (any Docker host; Oracle Cloud's free Arm VM is enough):

```bash
mkdir ~/finresearch && cd ~/finresearch
# copy deploy/.env.example to .env and fill it in (POSTGRES_PASSWORD, GEMINI_API_KEY, SEC_USER_AGENT)
```

In GitHub, create the `production` environment with secrets `DEPLOY_HOST`, `DEPLOY_USER` and `DEPLOY_SSH_KEY`, then
set the repository variable `DEPLOY_ENABLED=true`. The next green `main` deploys; run the Deploy workflow by hand
with an older `sha-…` tag to roll back.

## Tests

```bash
docker exec finresearch-postgres psql -U finresearch -c "CREATE DATABASE finresearch_test"   # once
python -m pytest                       # isolated *_test database, truncated after every test
cd frontend && npm run typecheck && npm run api:check
```

The suite covers the queue's concurrency guarantees (ten threads racing for one job, zombie-worker fencing, a real
`kill -9` of a worker process mid-job, graceful SIGTERM), the API contract, schema constraints, every metric formula,
XBRL extraction, filing parsing, and the full pipeline end to end with a fake SEC transport, a fake LLM and a
scripted tool-calling model: the agent's fan-out, its bounded revision loop, resume after a 429 without re-running
finished researchers, cancel mid-research, the trace API and the analyst chat's citation checks.

## Evaluation

```bash
python -m backend.evals.retrieval                          # retrieval quality: vector vs keyword vs hybrid vs reranked
python -m backend.evals.citations auto <job_id>            # coverage, quote verification, numeric consistency
python -m backend.evals.citations export <job_id> > evals/labels/MSFT.json
python -m backend.evals.citations score evals/labels/*.json # human-labelled citation correctness vs the 95% target
```

## Project layout

```text
backend/
  api/            routes, dependencies (dev identity until auth lands)
  services/       transactions live here: job submission, queue operations, reports
  repositories/   SQL, including the fenced queue updates (never commit)
  agent/          LangGraph research graph, researcher tools, Postgres checkpointer
  pipeline/       stage runner, ingestion stages, prompts and output schemas
  sources/        SEC EDGAR client, XBRL extraction, filing text parsing
  analysis/       metrics (Decimal), chunking, hybrid retrieval, verification
  llm/            provider adapter (Gemini): retry classification, model cool-downs, pacing
  costs/          cost ledger, dated price table, spend caps
  valuation/      fair-value engine, default assumptions, reference data, Treasury rate, delayed quote, backfill
  worker/         the worker process: claim, heartbeat, retry, release
  evals/          evidence-quality metrics and label scoring
database/migrations/   Alembic revisions (never edit an applied one)
frontend/              React app; design system in frontend/DESIGN.md
docs/                  STATUS.md, ADRs, INTERVIEW_NOTES.md
```

## Scope (v1)

US-listed, non-financial companies that file a 10-K, in USD. Prices come from Cboe's free delayed quote, which is
licensed for personal, non-commercial use (a commercial deployment needs a licensed feed), or from a price the reader
types; the written report makes no price claims, and there are no valuation multiples or price targets. Single development user until authentication (planned with deployment).
