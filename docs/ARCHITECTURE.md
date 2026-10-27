> **Superseded (2026-10-28).** This is the original August plan and is kept for history. Where it disagrees with
> the code, the code and the ADRs in `docs/adr/` win: the queue is Postgres-backed (ADR 0001), not Celery + Redis;
> the frontend is React, not Streamlit; embeddings are 768-d Gemini; submission returns 202 (ADR 0003).
> Start from `README.md` and `docs/STATUS.md`.

# FinResearch AI --- Architecture

> 🔒 **ARCHITECTURE FREEZE --- V1.0**
>
> This document is the source of truth for the architecture of
> `finresearch-ai`. Significant changes to frozen decisions should be
> discussed and agreed upon before implementation.

## 1. Project Overview

### 1.1 Objective

FinResearch AI is an agentic financial research platform for US
equities. A user submits an investment research question, and the system
asynchronously researches the company using financial data, SEC filings,
news, retrieval-augmented generation (RAG), deterministic valuation
models, risk analysis, evidence verification, and LLM synthesis.

### 1.2 Primary Goal

Demonstrate production-oriented AI and backend engineering through:

-   Agent orchestration
-   RAG and evidence provenance
-   Financial data processing
-   Deterministic valuation
-   Asynchronous job processing
-   PostgreSQL and pgvector
-   API design
-   Docker
-   AWS deployment
-   Testing and observability

### 1.3 V1 Market Scope

**US equities.**

The core domain will use provider abstractions so other markets can be
added later without rewriting the research engine.

------------------------------------------------------------------------

# 2. High-Level Architecture

``` text
                         ┌─────────────────────┐
                         │     Streamlit UI    │
                         │  Research Dashboard │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │       FastAPI       │
                         │      REST API       │
                         └──────────┬──────────┘
                                    │
                           Create Research Job
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Redis / Queue    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Background Worker  │
                         │   Celery + Python   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      LangGraph      │
                         │   Research Engine   │
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
       Financial Agent       Documents Agent         News Agent
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    ▼
                              RAG Agent
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  Valuation Agent         Risk Agent
                         │                     │
                         └──────────┬──────────┘
                                    ▼
                              Verification
                                    │
                                    ▼
                             LLM Synthesis
                                    │
                                    ▼
                      ┌─────────────────────────┐
                      │ PostgreSQL + pgvector   │
                      └────────────┬────────────┘
                                   │
                                   ▼
                              FastAPI
                                   │
                                   ▼
                             Streamlit UI
```

------------------------------------------------------------------------

# 3. Frozen Technology Stack

  Layer                 Technology          Purpose
  --------------------- ------------------- -----------------------------------------
  Frontend              Streamlit           Research dashboard
  API                   FastAPI             REST API
  Language              Python 3.12         Application language
  Agent orchestration   LangGraph           Research workflow
  LLM                   Gemini API          Reasoning, structured output, synthesis
  Embeddings            Gemini embeddings   Semantic retrieval
  Database              PostgreSQL          Persistent relational data
  Vector search         pgvector            RAG similarity search
  Queue                 Redis               Job/message broker
  Workers               Celery              Background execution
  Documents             pypdf               Initial PDF parsing
  Data processing       Pandas / NumPy      Financial calculations
  HTTP                  httpx               External API access
  Containers            Docker              Reproducible environments
  Cloud                 AWS                 Production deployment
  CI/CD                 GitHub Actions      Automated deployment
  Testing               pytest              Automated testing
  Code quality          Ruff / mypy         Linting, formatting, typing

### Deliberately excluded from V1

-   React
-   Kubernetes
-   Kafka
-   MongoDB
-   Managed vector database
-   Multiple LLM providers
-   Custom ML models
-   Brokerage/trading integration
-   Real-time trading infrastructure
-   Excessive microservices

------------------------------------------------------------------------

# 4. Research Workflow

``` text
Research Request
       │
       ▼
Research Planner
       │
 ┌─────┼─────┐
 ▼     ▼     ▼
Financial  Documents  News
 Agent      Agent     Agent
 └─────┬─────┘
       ▼
    RAG Agent
       │
 ┌─────┴─────┐
 ▼           ▼
Valuation   Risk
 Agent      Agent
 └─────┬─────┘
       ▼
 Verification
       │
       ├── Unsupported → Research / RAG retry
       │
       ▼
   Synthesis
       │
       ▼
 Final Report
```

Financial, document, and news research are designed to run independently
where possible.

------------------------------------------------------------------------

# 5. LangGraph State

The graph uses a shared `ResearchState` as temporary working memory.

``` text
ResearchState
│
├── context
├── request
├── plan
├── financial_data
├── documents[]
├── news[]
├── evidence[]
├── claims[]
├── valuation
├── risks[]
├── verification
├── synthesis
└── errors[]
```

## State ownership

  Component         Writes
  ----------------- ----------------------------
  Planner           `plan`
  Financial Agent   `financial_data`, `claims`
  Documents Agent   `documents`
  News Agent        `news`, `claims`
  RAG Agent         `evidence`, `claims`
  Valuation Agent   `valuation`, `claims`
  Risk Agent        `risks`, `claims`
  Verification      `verification`
  Synthesis         `synthesis`
  Any node          `errors`

LangGraph state is temporary workflow state. Persistent business data is
stored in PostgreSQL.

------------------------------------------------------------------------

# 6. Database Architecture

## 6.1 Entities

The V1 database contains:

``` text
users
research_jobs
agent_runs
financial_snapshots
documents
document_chunks
claims
evidence
claim_evidence
reports
```

## 6.2 Relationships

``` text
USER
 │
 └── 1:N → RESEARCH_JOB
                │
                ├── 1:N → AGENT_RUN
                ├── 1:N → FINANCIAL_SNAPSHOT
                ├── 1:N → CLAIM
                │              │
                │              └── N:M → EVIDENCE
                │                            │
                │                            └── N:1 → DOCUMENT
                │                                            │
                │                                            └── 1:N
                │                                                  │
                │                                           DOCUMENT_CHUNK
                │
                └── 1:1 → REPORT
```

## 6.3 Core principle

Structured financial data and unstructured source documents are stored
separately.

Claims maintain provenance through evidence back to source
documents/chunks.

------------------------------------------------------------------------

# 7. Database Schema Specification

This section is the **implementation contract** for the frozen V1 database design.

## 7.1 `users`

Stores application users. Authentication is intentionally deferred, but the user entity exists so research jobs can be associated with an owner.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique user identifier |
| `email` | VARCHAR(320) | NOT NULL, UNIQUE | User email |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Creation timestamp |

### Indexes
- Unique index on `email`.

## 7.2 `research_jobs`

The central persistent entity representing one research request and its execution lifecycle.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique research job |
| `user_id` | UUID | FK → `users.id`, NOT NULL | Job owner |
| `query` | TEXT | NOT NULL | Original research question |
| `company` | VARCHAR(255) | NOT NULL | Company name |
| `ticker` | VARCHAR(20) | NOT NULL | US equity ticker |
| `status` | VARCHAR(32) | NOT NULL | `queued`, `running`, `completed`, `failed` |
| `current_stage` | VARCHAR(64) | | Current workflow stage |
| `progress` | INTEGER | NOT NULL, 0–100 | Approximate job progress |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Creation timestamp |
| `started_at` | TIMESTAMP WITH TIME ZONE | | Execution start |
| `completed_at` | TIMESTAMP WITH TIME ZONE | | Completion timestamp |
| `error_message` | TEXT | | Terminal failure details |

### Indexes
- `user_id`
- `(user_id, created_at)`
- `status`

### Delete behavior
- User deletion → associated research jobs deleted.
- Research job deletion → dependent research data deleted according to the cascade rules below.

## 7.3 `agent_runs`

Records every meaningful agent execution belonging to a research job.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique agent run |
| `research_job_id` | UUID | FK → `research_jobs.id`, NOT NULL | Parent research job |
| `agent_name` | VARCHAR(64) | NOT NULL | Agent that executed |
| `status` | VARCHAR(32) | NOT NULL | Execution status |
| `started_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Start time |
| `completed_at` | TIMESTAMP WITH TIME ZONE | | Completion time |
| `duration_ms` | INTEGER | | Execution duration |
| `input_tokens` | INTEGER | | LLM input tokens |
| `output_tokens` | INTEGER | | LLM output tokens |
| `model` | VARCHAR(128) | | Model used |
| `estimated_cost` | NUMERIC(12,8) | | Estimated LLM/API cost |
| `error_message` | TEXT | | Error details |
| `metadata` | JSONB | | Agent-specific metadata |

### Indexes
- `research_job_id`
- `(research_job_id, agent_name)`
- `(research_job_id, started_at)`

The token/cost fields support the project's explicit cost-monitoring requirement.

## 7.4 `financial_snapshots`

Stores structured financial data separately from unstructured documents.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique snapshot |
| `research_job_id` | UUID | FK → `research_jobs.id`, NOT NULL | Associated research |
| `ticker` | VARCHAR(20) | NOT NULL | Equity ticker |
| `period` | VARCHAR(32) | NOT NULL | Reporting period |
| `period_end_date` | DATE | NOT NULL | Period end |
| `currency` | VARCHAR(8) | NOT NULL | Reporting currency |
| `revenue` | NUMERIC(20,4) | | Revenue |
| `net_income` | NUMERIC(20,4) | | Net income |
| `operating_income` | NUMERIC(20,4) | | Operating income |
| `free_cash_flow` | NUMERIC(20,4) | | Free cash flow |
| `eps` | NUMERIC(20,6) | | Earnings per share |
| `gross_margin` | NUMERIC(10,6) | | Gross margin |
| `operating_margin` | NUMERIC(10,6) | | Operating margin |
| `cash` | NUMERIC(20,4) | | Cash/cash equivalents |
| `debt` | NUMERIC(20,4) | | Debt |
| `source` | VARCHAR(128) | NOT NULL | Data provider/source |
| `source_reference` | TEXT | | Provider-specific reference |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Record creation time |

### Indexes
- `(ticker, period_end_date)`
- `research_job_id`
- `(ticker, period, period_end_date)`

The schema can be extended with additional financial metrics when the Financial Agent requirements are implemented; V1 should not pre-populate speculative columns.

## 7.5 `documents`

Represents an external source document or article.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique document |
| `source_type` | VARCHAR(64) | NOT NULL | `annual_report`, `10-q`, `8-k`, `news`, etc. |
| `title` | TEXT | NOT NULL | Document title |
| `url` | TEXT | NOT NULL | Canonical source URL |
| `publisher` | VARCHAR(255) | | Publisher/source organization |
| `published_at` | TIMESTAMP WITH TIME ZONE | | Publication timestamp |
| `document_date` | DATE | | Document/report date |
| `content_hash` | VARCHAR(128) | NOT NULL | Deduplication/content identity |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Ingestion timestamp |

### Indexes
- Unique index on `content_hash`
- `source_type`
- `publisher`
- `document_date`

Documents are reusable source entities and therefore do not belong directly to a single research job.

## 7.6 `document_chunks`

Stores retrievable portions of documents and their vector embeddings.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique chunk |
| `document_id` | UUID | FK → `documents.id`, NOT NULL | Parent document |
| `chunk_index` | INTEGER | NOT NULL | Chunk order within document |
| `content` | TEXT | NOT NULL | Chunk text |
| `embedding` | VECTOR | | Gemini embedding |
| `metadata` | JSONB | | Chunk-specific metadata |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Creation timestamp |

### Constraints
- Unique `(document_id, chunk_index)`.

### Indexes
- `document_id`
- Vector similarity index on `embedding`, selected after benchmarking the actual embedding dimension and query workload.

We deliberately do not hard-code the vector dimension until the embedding model is finalized during implementation.

## 7.7 `claims`

Represents a factual or analytical claim generated during research.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique claim |
| `research_job_id` | UUID | FK → `research_jobs.id`, NOT NULL | Associated research |
| `agent_run_id` | UUID | FK → `agent_runs.id` | Agent that generated the claim |
| `claim_text` | TEXT | NOT NULL | Claim statement |
| `claim_type` | VARCHAR(64) | NOT NULL | Financial, operational, risk, etc. |
| `confidence` | NUMERIC(5,4) | 0–1 | Agent confidence |
| `verification_status` | VARCHAR(32) | NOT NULL | Verification state |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Creation timestamp |

### Indexes
- `research_job_id`
- `agent_run_id`
- `(research_job_id, verification_status)`

Claims are not authoritative simply because an LLM generated them. Their evidentiary support is represented through `claim_evidence`.

## 7.8 `evidence`

Represents a specific piece of source evidence supporting one or more claims.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique evidence item |
| `document_id` | UUID | FK → `documents.id`, NOT NULL | Source document |
| `document_chunk_id` | UUID | FK → `document_chunks.id` | Source chunk |
| `excerpt` | TEXT | NOT NULL | Relevant source excerpt |
| `page_number` | INTEGER | | Page number when available |
| `source_url` | TEXT | | Direct source URL |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Creation timestamp |

### Indexes
- `document_id`
- `document_chunk_id`

## 7.9 `claim_evidence`

Junction table implementing the many-to-many relationship between claims and evidence.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `claim_id` | UUID | FK → `claims.id`, NOT NULL | Supported claim |
| `evidence_id` | UUID | FK → `evidence.id`, NOT NULL | Supporting evidence |
| `relevance_score` | NUMERIC(5,4) | 0–1 | Evidence relevance |

### Constraints
- Composite primary key: `(claim_id, evidence_id)`.

### Indexes
- `claim_id`
- `evidence_id`

This table is the core of the claim-to-evidence provenance graph.

## 7.10 `reports`

Stores the final synthesized research output.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID | PK | Unique report |
| `research_job_id` | UUID | FK → `research_jobs.id`, UNIQUE, NOT NULL | One report per research job |
| `executive_summary` | TEXT | NOT NULL | Executive summary |
| `investment_thesis` | TEXT | | Final thesis |
| `valuation_summary` | JSONB | | Bull/base/bear valuation results |
| `risk_summary` | JSONB | | Structured risk results |
| `full_report` | JSONB | NOT NULL | Complete structured report |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Report creation time |

### Indexes
- Unique index on `research_job_id`.

## 7.11 Relationship and Cascade Rules

The intended ownership hierarchy is:

```text
users
  │
  └── research_jobs
          ├── agent_runs
          ├── financial_snapshots
          ├── claims
          │     └── claim_evidence
          └── reports

documents
  └── document_chunks

documents
  └── evidence
          └── claim_evidence
```

### Cascades

Deleting a `research_job` should cascade to:
- `agent_runs`
- `financial_snapshots`
- `claims`
- `claim_evidence` associated with those claims
- `reports`

Deleting a `document` should cascade to:
- `document_chunks`
- `evidence`
- corresponding `claim_evidence`

However, deleting a research job **must not delete its documents**, because documents may be reused across research jobs.

## 7.12 Identifier Strategy

All primary keys use **UUIDs**.

Reasons:
- Safe for distributed/background processing.
- Avoids predictable sequential public identifiers.
- Works well across independently created jobs and agent runs.
- Keeps API identifiers decoupled from row counts.

## 7.13 Timestamp Strategy

Persistent timestamps use:

```text
TIMESTAMP WITH TIME ZONE
```

and are stored in UTC. The application converts timestamps for display at the UI boundary.

## 7.14 JSONB Strategy

JSONB is used only where the structure is genuinely flexible:
- Agent metadata
- Document/chunk metadata
- Valuation summary
- Risk summary
- Full report

Core relational entities and frequently queried fields remain explicit columns.

# 8. API V1

Base path:

``` text
/api/v1
```

## Endpoints

  Method   Endpoint                        Purpose
  -------- ------------------------------- -------------------------
  POST     `/research`                     Create research job
  GET      `/research/{job_id}`            Get job status
  GET      `/research/{job_id}/report`     Get final report
  GET      `/research/{job_id}/evidence`   Get supporting evidence
  DELETE   `/research/{job_id}`            Delete research job

## Research creation

``` json
{
  "company": "NVDA",
  "question": "Should I invest in NVIDIA for the next 5 years?",
  "horizon_years": 5
}
```

The endpoint returns `202 Accepted` because research executes
asynchronously.

## Job lifecycle

``` text
QUEUED
   │
   ▼
RUNNING
   │
   ├──→ FAILED
   │
   ▼
COMPLETED
```

## Research stages

``` text
PLANNING
FINANCIAL_RESEARCH
DOCUMENT_RESEARCH
NEWS_RESEARCH
RAG
VALUATION
RISK_ANALYSIS
VERIFICATION
SYNTHESIS
```

------------------------------------------------------------------------

# 9. External Data and Tools

## Core V1 sources

### SEC EDGAR

Primary source for:

-   10-K
-   10-Q
-   8-K
-   Company submissions
-   XBRL financial facts

### Financial Data Provider

Provides market data and supplementary financial information.

The provider will sit behind a `FinancialDataProvider` abstraction.

### News Provider

Provides recent company and market news.

The provider will sit behind a `NewsProvider` abstraction.

### Gemini API

Used for:

-   Research planning
-   Agent reasoning
-   Structured outputs
-   Risk reasoning
-   Final synthesis
-   Embeddings

### FRED

Optional supporting source for macroeconomic information such as
interest rates and economic indicators.

------------------------------------------------------------------------

# 10. RAG Architecture

RAG is implemented inside our system rather than delegated to a hosted
RAG service.

``` text
Source Document
      │
      ▼
Document Parsing
      │
      ▼
Chunking
      │
      ▼
Gemini Embeddings
      │
      ▼
PostgreSQL + pgvector
      │
      ▼
Semantic Retrieval
      │
      ▼
Evidence
```

The actual documents are stored separately from LangGraph state.

------------------------------------------------------------------------

# 11. Valuation Architecture

## Core principle

**LLMs do not perform the valuation mathematics.**

The LLM/research agents produce evidence-backed assumptions.

A deterministic Python valuation engine performs the calculations.

``` text
Historical Data
      +
Company Research
      +
Industry Research
      +
Management Guidance
      +
Market/Macro Data
      │
      ▼
Evidence-backed Assumptions
      │
      ▼
Python Valuation Engine
      │
 ┌────┼────┐
 ▼    ▼    ▼
Bull Base Bear
```

## DCF

The engine will calculate:

``` text
Revenue Forecast
      ↓
Operating Profit
      ↓
Free Cash Flow
      ↓
Discount Rate / WACC
      ↓
Terminal Value
      ↓
Enterprise Value
      ↓
Equity Value
      ↓
Intrinsic Value Per Share
```

## Bull / Base / Bear

Scenarios differ through explicit assumptions such as:

-   Revenue growth
-   Operating margins
-   WACC
-   Terminal growth

Assumptions must be supported by research where possible.

### WACC

WACC will be calculated using market and financial inputs rather than
invented by the LLM.

### Terminal growth

Terminal growth will be constrained by a defined model policy and
macroeconomic context.

------------------------------------------------------------------------

# 12. Evidence and Verification

Major claims should be traceable to supporting evidence.

``` text
CLAIM
  │
  ▼
EVIDENCE
  │
  ▼
DOCUMENT / DOCUMENT CHUNK
```

Verification checks whether generated claims are supported.

``` text
Claims
  ↓
Evidence Retrieval
  ↓
Verification
  │
  ├── PASS → Synthesis
  │
  └── FAIL → Research / RAG retry
```

Retries will have a defined maximum to prevent infinite loops.

------------------------------------------------------------------------

# 13. Async Architecture

Long-running research must not block FastAPI.

``` text
Streamlit
    ↓
FastAPI
    ↓
Redis
    ↓
Celery Worker
    ↓
LangGraph
    ↓
PostgreSQL
```

The API immediately returns a `job_id`.

The frontend can poll the job status endpoint while the worker executes
the research.

------------------------------------------------------------------------

# 14. Cost, Performance, and Quality Principles

These are explicit project constraints.

### Priority order

1.  **Correctness and research quality**
2.  **Performance and efficiency**
3.  **Architecture and scalability**
4.  **Cost optimization**

Cost reduction must not compromise the quality or requirements of the
system.

### Cost strategies

-   Prefer local Docker infrastructure during development.
-   Use low-cost/free data sources where quality is sufficient.
-   Use cheaper LLM models for low-complexity tasks.
-   Reserve stronger models for tasks where quality materially benefits.
-   Cache reusable data and research results where appropriate.
-   Minimize redundant LLM calls.
-   Track token usage and estimated LLM cost.
-   Delay paid AWS infrastructure until deployment is necessary.
-   Avoid unnecessary managed services.
-   Abstract third-party providers to avoid vendor lock-in.

------------------------------------------------------------------------

# 15. Deployment Architecture

Target V1 deployment:

``` text
                    AWS
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
   Streamlit       FastAPI      Celery Worker
                      │             │
                      └──────┬──────┘
                             ▼
                          Redis
                             │
                             ▼
                    PostgreSQL + pgvector
                             │
                             ▼
                            S3
```

Docker and GitHub Actions will be used for packaging and CI/CD.

The deployment will be sized conservatively to minimize unnecessary
recurring costs.

------------------------------------------------------------------------

# 16. Repository Structure

``` text
finresearch-ai/
│
├── backend/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── repositories/
│   ├── services/
│   └── main.py
│
├── agents/
│   ├── planner/
│   ├── financial/
│   ├── documents/
│   ├── news/
│   ├── rag/
│   ├── valuation/
│   ├── risk/
│   └── synthesis/
│
├── workflows/
│   └── research_graph.py
│
├── workers/
│   └── tasks.py
│
├── frontend/
│   └── streamlit/
│
├── database/
│   ├── migrations/
│   └── seed/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── config/
├── scripts/
├── docker/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

# 17. V1 Scope

## Included

-   US equity research
-   Financial data research
-   SEC/annual report research
-   News research
-   RAG with pgvector
-   Evidence provenance
-   Financial calculations
-   DCF valuation
-   Bull/base/bear scenarios
-   Risk analysis
-   Claim verification
-   LLM synthesis
-   Async jobs
-   FastAPI
-   Streamlit
-   PostgreSQL
-   Redis
-   Celery
-   Docker
-   Testing
-   AWS deployment
-   CI/CD

## Explicitly excluded

-   Brokerage integration
-   Automated trading
-   Real-time trading
-   Portfolio execution
-   Kubernetes
-   Large-scale distributed infrastructure
-   Multiple market implementations
-   Custom ML model training

------------------------------------------------------------------------

# 18. Architectural Decisions

  -----------------------------------------------------------------------
  Decision                            Rationale
  ----------------------------------- -----------------------------------
  Streamlit over React                Frontend is not the primary project
                                      objective; reduces development time

  PostgreSQL + pgvector               One database for relational data
                                      and vector retrieval

  LangGraph                           Explicit agent workflow and state
                                      orchestration

  Redis + Celery                      Decouple long-running research from
                                      FastAPI

  Python valuation engine             Deterministic, auditable financial
                                      calculations

  SEC as primary filing source        High-quality primary US filing data

  US equities for V1                  Strong public data ecosystem and
                                      useful research test cases

  Provider abstractions               Avoid vendor lock-in and enable
                                      future markets/providers

  Async research jobs                 Research can take tens of
                                      seconds/minutes

  Evidence provenance                 Improve trustworthiness and
                                      interview value

  Python 3.12                         Dependency compatibility and
                                      stability
  -----------------------------------------------------------------------

------------------------------------------------------------------------

