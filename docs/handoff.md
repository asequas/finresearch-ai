# FinResearch AI — Complete Portable Project Context

**Purpose:** Handoff document for continuing development in a new ChatGPT conversation.

**Project:** `finresearch-ai`  
**Developer:** Abishek Arun  
**Last verified working session:** August 30, 2026  
**Environment:** MacBook Air, macOS, Python 3.12.6 virtual environment  
**Current Git branch:** `main`  
**Last verified full test suite:** 14 passed, 1 warning  
**Next planned phase:** Phase 3 — Background Execution and Research Orchestration

---

# 1. Project Overview

FinResearch AI is an Agentic RAG-based AI Financial Research Analyst.

The goal is to build a system that accepts a research question about a US-listed company and produces a comprehensive, evidence-backed financial research report.

Example query:

> Should I invest in Apple?

The system should eventually research the company using multiple sources, analyze financial performance, retrieve relevant documents, investigate news, assess valuation and risk, verify claims against evidence, and synthesize a final report.

The application is intended to demonstrate real backend engineering, system design, agentic AI, RAG, data engineering, and deployment skills.

This is a long-term portfolio project, not merely a demo that sends a prompt to an LLM.

## Core product capabilities planned

1. Submit a financial research request.
2. Create and persist a research job.
3. Execute research asynchronously.
4. Retrieve financial data and historical financial statements.
5. Research SEC filings and annual reports.
6. Gather relevant financial news.
7. Index documents and perform retrieval-augmented generation.
8. Run valuation and risk analysis.
9. Verify claims against supporting evidence.
10. Synthesize a comprehensive report.
11. Track job status and agent execution.
12. Display research reports through a Streamlit frontend.

The intended market coverage is the **US stock market**.

---

# 2. Non-negotiable Development Principles

These constraints should guide all future implementation decisions.

## Cost discipline

Keep development costs as close to ₹0 as practical.

Prioritize:
- Local development and free infrastructure.
- Free or inexpensive financial data sources.
- Free-tier or low-cost LLM APIs where appropriate.
- Local models where they offer a reasonable cost/performance trade-off.
- Caching to avoid duplicate API calls and LLM inference.
- Efficient prompts, context windows, and token usage.
- Small, inexpensive AWS deployments when cloud hosting becomes necessary.

**Do not optimize cost by blindly sacrificing performance or reliability.** Explain the trade-off and choose the most appropriate option.

Avoid adding paid services, unnecessary infrastructure, or extra dependencies without a clear reason.

## Engineering quality

- Use a layered, maintainable architecture.
- Add automated tests as features are implemented.
- Prefer explicit interfaces and clear ownership of responsibilities.
- Persist important application state.
- Design for failure, retries, observability, and idempotency where needed.
- Keep Git history organized with meaningful commits.
- Do not declare a phase complete until its acceptance criteria are met.

## Interview preparation — critical requirement

The developer must learn to explain and defend every significant system design and architecture decision.

For each meaningful decision, teach:

1. The problem being solved.
2. The chosen design and why it fits this project.
3. Alternatives considered.
4. Trade-offs involving cost, latency, consistency, scalability, and complexity.
5. Failure scenarios and recovery strategies.
6. Likely interview questions and strong answers.
7. When a different design would be more appropriate.

Where useful, ask the developer to propose a design before explaining the preferred solution. Critique the answer constructively and teach the underlying principles.

The goal is not merely to finish FinResearch AI. The goal is for the developer to confidently defend the architecture in backend, system design, and AI engineering interviews.

---

# 3. Technology Stack

## Implemented or established

| Component | Technology | Current status |
|---|---|---|
| Programming language | Python | Implemented |
| API framework | FastAPI | Working |
| Request/response validation | Pydantic | Working |
| ORM | SQLAlchemy | Working |
| Database | PostgreSQL 17 | Running locally |
| Vector extension | pgvector 0.8.6 | Installed and verified |
| Database migrations | Alembic | Working |
| Testing | pytest | Working |
| HTTP API testing | FastAPI TestClient | Working |
| Containerization | Docker Compose | PostgreSQL running locally |
| Version control | Git | Initial commit exists |

## Planned or intended

| Component | Technology | Purpose |
|---|---|---|
| Frontend | Streamlit | Research dashboard |
| Agent workflow orchestration | LangGraph | Coordinate research stages |
| Background workers | Initially planned with Celery; final implementation choice remains open | Execute long-running research jobs |
| Job queue | Redis or another suitable queue | Dispatch and coordinate background work |
| Vector retrieval | PostgreSQL + pgvector | Semantic document retrieval |
| Financial data | US market data providers | Prices and financial fundamentals |
| Company filings | SEC/annual reports | Primary-source financial evidence |
| News ingestion | Suitable free/low-cost news sources | Recent company research |
| Deployment | Docker and potentially AWS | Hosting |
| CI/CD | GitHub Actions or equivalent | Automated testing and deployment |

**Important:** Do not assume the background task system, Redis integration, LangGraph workflow, financial APIs, or AWS deployment have already been implemented. They are part of the planned architecture.

---

# 4. Development Environment

The project directory is:

`~/Desktop/finresearch-ai`

Python environment:

- Installed project interpreter: Python 3.12.6.
- Virtual environment: `.venv`.
- Activate with `source .venv/bin/activate`.
- Run tests using `python -m pytest`, not bare `pytest`, to avoid interpreter/path confusion.

Typical setup:

```bash
cd ~/Desktop/finresearch-ai
source .venv/bin/activate
```

PostgreSQL runs through Docker Compose.

Known local database configuration:

```text
Database: finresearch
User: finresearch
Host: localhost
Port: 5432
```

SQLAlchemy URL used during development:

```text
postgresql+psycopg://finresearch:finresearch_dev@localhost:5432/finresearch
```

The database credentials above are development credentials. Never use them as production credentials.

The PostgreSQL container is named:

```text
finresearch-postgres
```

Connect to it with:

```bash
docker exec -it finresearch-postgres \
  psql -U finresearch -d finresearch
```

Useful database commands:

```sql
\dt
\di
\pset pager off
SELECT version_num FROM alembic_version;
```

To check migration drift:

```bash
alembic check
```

At the last recorded check, Alembic reported:

```text
No new upgrade operations detected.
```

The initial database schema was successfully migrated.

---

# 5. Repository Structure

The following structure is established or was explicitly observed during development. Some planned directories may have additional files that have not yet been verified.

```text
finresearch-ai/
│
├── backend/
│   ├── __init__.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── research.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── database.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── research_job.py
│   │   ├── agent_run.py
│   │   ├── document.py
│   │   ├── document_chunk.py
│   │   ├── evidence.py
│   │   ├── claim.py
│   │   ├── claim_evidence.py
│   │   ├── financial_snapshot.py
│   │   └── report.py
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── research_job.py
│   │
│   ├── schemas/
│   │   └── research.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── research_job.py
│   │
│   └── main.py
│
├── database/
│   └── migrations/
│       ├── env.py
│       ├── README
│       ├── script.py.mako
│       └── versions/
│           └── 411c859e2482_create_initial_schema.py
│
├── tests/
│   └── integration/
│       ├── test_database.py
│       ├── test_research_job_repository.py
│       ├── test_research_job_service.py
│       └── test_research_api.py
│
├── alembic.ini
├── pyproject.toml
├── docker-compose.yml
├── .env.example
└── .venv/
```

The tree is a handoff snapshot, not a verified listing of the current filesystem. Inspect `git status` and the actual repository before modifying or creating files.

---

# 6. Database Architecture

The initial migration created the following eleven tables, including Alembic's migration tracking table.

## Application tables

### 1. `users`

Stores application users.

Important columns:
- `id`: UUID primary key.
- `email`: unique email address.
- `created_at`: timezone-aware timestamp.

### 2. `research_jobs`

Tracks a research request and its lifecycle.

Important columns:
- `id`: UUID primary key.
- `user_id`: foreign key to `users`.
- `query`: original research question.
- `company`: company name.
- `ticker`: stock ticker.
- `status`: job status.
- `current_stage`: current research stage.
- `progress`: integer progress indicator.
- `created_at`, `started_at`, `completed_at`.
- `error_message`: failure details.

Indexes include:
- `ix_research_jobs_status`
- `ix_research_jobs_user_created`

The status model is:

```python
class ResearchJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

The intended lifecycle is:

```text
queued → running → completed
                  ↘ failed
```

Additional states, retries, and cancellation semantics have not yet been fully designed.

### 3. `agent_runs`

Tracks individual agent executions associated with a research job.

Important fields:
- `research_job_id`
- `agent_name`
- `status`
- `started_at`, `completed_at`
- `duration_ms`
- `input_tokens`, `output_tokens`
- `model`
- `estimated_cost`
- `error_message`
- JSON metadata

This table will be valuable for observability, cost tracking, and debugging.

### 4. `documents`

Stores metadata for ingested research documents.

Important fields:
- `source_type`
- `title`
- `url`
- `publisher`
- `published_at`
- `document_date`
- `content_hash`
- `created_at`

`content_hash` is unique to support document deduplication.

### 5. `document_chunks`

Stores text chunks associated with documents.

Important fields:
- `document_id`
- `chunk_index`
- `content`
- `embedding`
- JSON metadata
- `created_at`

The embedding column is:

```text
vector(768)
```

The database was verified to recognize the PostgreSQL `vector` type.

The combination of `document_id` and `chunk_index` is unique.

**Design implication:** The embedding provider/model must produce 768-dimensional embeddings unless the schema is deliberately migrated. Do not switch embedding models without considering dimension compatibility and re-embedding existing data.

### 6. `evidence`

Stores evidence excerpts associated with source documents and optionally document chunks.

Important fields:
- `document_id`
- `document_chunk_id`
- `excerpt`
- `page_number`
- `source_url`
- `created_at`

The chunk reference uses `ON DELETE SET NULL`; the document reference uses `ON DELETE CASCADE`.

### 7. `claims`

Stores claims produced during research.

Important fields:
- `research_job_id`
- `agent_run_id`
- `claim_text`
- `claim_type`
- `confidence`
- `verification_status`
- `created_at`

### 8. `claim_evidence`

A many-to-many association between claims and supporting evidence.

Fields:
- `claim_id`
- `evidence_id`
- `relevance_score`

The pair `(claim_id, evidence_id)` is the composite primary key.

This provides the foundation for traceable, evidence-backed financial research.

### 9. `financial_snapshots`

Stores financial metrics associated with a research job and ticker.

Important fields:
- `research_job_id`
- `ticker`
- `period`
- `period_end_date`
- `currency`
- `revenue`
- `net_income`
- `operating_income`
- `free_cash_flow`
- `eps`
- `gross_margin`
- `operating_margin`
- `cash`
- `debt`
- `source`
- `source_reference`
- `created_at`

Metrics use appropriate `Numeric` types for financial precision.

### 10. `reports`

Stores the generated research report.

Important fields:
- `research_job_id`
- `executive_summary`
- `investment_thesis`
- `valuation_summary`
- `risk_summary`
- `full_report`
- `created_at`

The report has a unique constraint on `research_job_id`, giving each job at most one report in the initial design.

Revisit this if we later need report versioning, regeneration history, or multiple report formats.

### 11. `alembic_version`

Tracks the applied migration revision.

The initial migration was recorded as:

```text
411c859e2482
```

## Foreign-key and deletion behavior

The schema uses foreign keys and deliberate deletion policies:
- User deletion cascades to their research jobs.
- Research job deletion cascades to associated agent runs, evidence-related research data, snapshots, claims, and reports where configured.
- Document deletion cascades to its chunks and evidence records.
- Evidence deletion cascades to claim-evidence associations.
- Agent run deletion sets associated claim references to null.

These relationships should be reviewed before production deployment. In particular, user deletion, document retention, and report retention need explicit product policies.

---

# 7. Database and Migration Work Completed

The initial schema was generated using Alembic and applied successfully.

Verified database tables:

```text
agent_runs
alembic_version
claim_evidence
claims
document_chunks
documents
evidence
financial_snapshots
reports
research_jobs
users
```

Verified:
- PostgreSQL is accessible.
- The migration is applied.
- `document_chunks.embedding` is `vector(768)`.
- Expected primary-key, unique, and secondary indexes exist.
- Alembic can compare the ORM metadata against the database.
- Database integration tests pass.

During setup, a few issues were resolved:

1. Incorrect enum import: Python's `Enum` and SQLAlchemy's `Enum` were accidentally confused.
2. Enum serialization: job statuses needed consistent lowercase values.
3. Timezone-aware defaults: `datetime.now(timezone.utc)` was adopted instead of deprecated `datetime.utcnow()`.
4. Missing `timezone` imports caused a `NameError`, which was fixed.
5. Model metadata and database schema were aligned until `alembic check` reported no differences.

Do not recreate the initial migration or reset the database unnecessarily. Extend the schema using new Alembic revisions when required.

---

# 8. Current Layered Backend Architecture

The implemented backend follows this structure:

```text
HTTP Client
    │
    ▼
FastAPI Router
    │
    ▼
Pydantic Request / Response Schemas
    │
    ▼
Service Layer
    │
    ▼
Repository Layer
    │
    ▼
SQLAlchemy Session
    │
    ▼
PostgreSQL
```

## Responsibilities

### API layer

Responsible for:
- HTTP routing.
- Request validation integration.
- Dependency injection.
- HTTP response codes.
- Translating missing resources into HTTP 404 responses.

It should not contain the entire business workflow.

### Schema layer

Uses Pydantic for request and response validation.

The established request model is:

```python
ResearchCreateRequest(
    query="Should I invest in Apple?",
    company="Apple Inc.",
    ticker="AAPL",
)
```

Empty research queries are rejected by validation.

### Service layer

Responsible for application-level behavior and coordinating repository operations.

### Repository layer

Responsible for persistence operations involving SQLAlchemy models.

### Database layer

Provides SQLAlchemy session and engine configuration.

### Models

Represent the persisted entities and their relationships.

---

# 9. Implemented API

FastAPI is configured in `backend/main.py` with the application title `FinResearch AI` and version `0.1.0`.

## Health endpoint

```http
GET /health
```

Expected:

```json
{
  "status": "ok"
}
```

## Create a research job

```http
POST /api/v1/research
Content-Type: application/json
```

Request:

```json
{
  "query": "Should I invest in Apple?",
  "company": "Apple Inc.",
  "ticker": "AAPL"
}
```

Verified response:

```json
{
  "id": "83f94335-a55b-4fdd-b2f5-d394fc7b2790",
  "query": "Should I invest in Apple?",
  "company": "Apple Inc.",
  "ticker": "AAPL",
  "status": "queued",
  "current_stage": null,
  "progress": 0
}
```

The UUID above is an example from the development session, not a fixed identifier.

Expected successful HTTP status:

```text
201 Created
```

## Retrieve a research job

```http
GET /api/v1/research/{job_id}
```

Verified behavior:
- Existing job: `200 OK`.
- Nonexistent job: `404 Not Found`.
- Invalid request data: `422 Unprocessable Entity`.

## Swagger documentation

Open the locally running application at:

```text
http://127.0.0.1:8000/docs
```

Run the API with:

```bash
uvicorn backend.main:app --reload
```

---

# 10. Important Transaction-Boundary Bug We Fixed

This is an important architectural lesson and should be remembered.

Initially, creating a job through POST returned `201 Created`, but immediately retrieving that job returned `404`.

The root cause was that the repository executed:

```python
session.add(job)
session.flush()
return job
```

`flush()` sends pending SQL statements to the database inside the current transaction. It does not commit the transaction.

The request-scoped database session closed without committing, so the insert was rolled back.

The API appeared to create the job successfully, but the row was not persisted.

## Fix applied

The service was updated to commit and refresh the new job:

```python
job = self.repository.create(
    session,
    user_id=user_id,
    query=request.query,
    company=request.company,
    ticker=request.ticker,
)

session.commit()
session.refresh(job)

return job
```

The repository remains responsible for persistence operations, not transaction ownership.

**Current design caveat:** We established service-owned transaction behavior for creation. We have not yet audited every service method for transaction consistency, rollback handling, or multi-operation atomicity. Do that before expanding into complex orchestration.

Interview takeaway:

> A successful SQLAlchemy `flush()` does not guarantee durable persistence. Transaction boundaries must be explicit and owned by a clearly defined layer.

The API integration tests caught this bug, and the corrected implementation passed the tests.

---

# 11. Development Authentication — Temporary

The development implementation uses a temporary user dependency that looks up or creates:

```text
dev@finresearch.local
```

The current API uses that user to associate new research jobs with a user record.

This is development-only behavior.

Not yet implemented:
- Real authentication.
- Password or identity-provider flows.
- JWT/session handling.
- User authorization.
- Per-user resource ownership checks.
- Production identity management.

Before production, replace the development-user dependency with a real authenticated-user dependency.

**Security requirement:** A user must not be able to retrieve another user's research job simply by guessing or obtaining its UUID. The GET endpoint currently needs a proper authorization/ownership check when authentication is introduced.

---

# 12. Automated Tests

The last recorded full regression run was:

```text
14 passed, 1 warning
```

All 14 tests passed.

## Test breakdown

| Test file | Number of passing tests |
|---|---:|
| `tests/integration/test_database.py` | 1 |
| `tests/integration/test_research_job_repository.py` | 4 |
| `tests/integration/test_research_job_service.py` | 5 |
| `tests/integration/test_research_api.py` | 4 |
| **Total** | **14** |

## Run the full suite

```bash
python -m pytest -v
```

## Run the API tests

```bash
python -m pytest tests/integration/test_research_api.py -v
```

## Run repository tests

```bash
python -m pytest tests/integration/test_research_job_repository.py -v
```

## Run service tests

```bash
python -m pytest tests/integration/test_research_job_service.py -v
```

## Known warning

The full suite reports:

```text
StarletteDeprecationWarning:
Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

It does not cause the tests to fail.

This dependency compatibility warning was intentionally deferred. Before changing dependencies, inspect the installed FastAPI, Starlette, and HTTP client versions, their compatibility constraints, and the recommended migration path. Do not blindly install `httpx2` without checking compatibility.

---

# 13. Git and Checkpoint Status

The initial database foundation was committed as:

```text
967c5a2 feat: complete database foundation
```

At that time, the working tree was clean.

Subsequently, Phase 2 added or modified:
- Pydantic schemas.
- Research job service.
- FastAPI application.
- API dependencies.
- Research routes.
- API integration tests.
- Transaction handling for research-job creation.

The full test suite then reached 14 passing tests.

**Important: The Phase 2 commit was proposed but not confirmed in the recorded conversation. Do not assume the latest work is committed.**

At the beginning of the next session, run:

```bash
cd ~/Desktop/finresearch-ai
source .venv/bin/activate

git status
git log -5 --oneline
python -m pytest -v
```

Inspect the working tree before staging or committing.

If Phase 2 changes are still uncommitted and the regression suite passes, create the checkpoint:

```bash
git add .
git commit -m "feat: complete research job API layer"
```

Then verify:

```bash
git status
```

Do not accidentally stage secrets, `.env` files, virtual-environment contents, generated artifacts, or unrelated files.

---

# 14. Milestones and Phase Tracking

## Phase 1 — Database Foundation

**Status: Completed.**

Delivered:
- PostgreSQL + pgvector.
- SQLAlchemy models.
- Alembic migrations.
- Initial relational schema.
- Database integration test.
- Initial Git commit.

## Phase 2 — Backend Application Layer

**Implementation status: Functionally complete; Git checkpoint needs verification.**

Delivered:
- Pydantic request/response schemas.
- Research job repository.
- Research job service.
- FastAPI application.
- API dependency injection.
- POST research endpoint.
- GET research endpoint.
- Request validation.
- Not-found handling.
- Automated integration tests.
- Transaction-boundary fix.

Last recorded acceptance run:

```text
14 passed, 1 warning
```

## Phase 3 — Background Execution and Research Orchestration

**Status: Not yet implemented. This is the next phase.**

The first milestone is to turn the current job-management API into a system that can accept a research request and execute the work asynchronously.

Proposed high-level flow:

```text
Client
  │
  ▼
POST /api/v1/research
  │
  ▼
Validate request
  │
  ▼
Persist research job
  │
  ▼
Enqueue background work
  │
  ▼
Return 202 Accepted
  │
  ▼
Background worker
  │
  ▼
Research orchestrator
  │
  ├── Planning
  ├── Financial research
  ├── Document research
  ├── News research
  ├── RAG
  ├── Valuation
  ├── Risk analysis
  ├── Verification
  └── Synthesis
          │
          ▼
    Persist report
          │
          ▼
   Mark job completed
```

This is the intended direction, not an already implemented pipeline.

Do not implement every agent in one giant step. Begin by designing and implementing a reliable asynchronous job lifecycle.

---

# 15. Phase 3 — Architecture Questions to Resolve

Before implementing the background worker, discuss these decisions explicitly.

## A. Why asynchronous execution?

Research can take tens of seconds or minutes. The HTTP request should not remain open for the entire research pipeline.

Questions:
- Why not perform all research inside the POST handler?
- What response should the API return?
- How does the client poll for status?
- How do we handle a client disconnect?

## B. Background execution mechanism

Candidates include:
- FastAPI `BackgroundTasks`.
- Celery with Redis.
- Another durable queue/worker architecture.

Do not select a solution merely because it is familiar.

Evaluate:
- Durability.
- Retry behavior.
- Worker concurrency.
- Operational complexity.
- Cost.
- Delivery guarantees.
- Ease of local development.
- Suitability for long-running LLM workflows.

A simple in-process background task may be useful for a prototype, but it does not provide the same durability and independent scaling as a properly configured queue and worker system.

## C. Database and queue consistency

A critical failure scenario:

1. The job is committed to PostgreSQL.
2. The application crashes before the task is enqueued.

Or the reverse:

1. The task is enqueued.
2. The database transaction fails.

Discuss how to avoid jobs being permanently stranded or workers receiving invalid jobs. The transactional outbox pattern may eventually be appropriate, but assess its complexity against the project's actual requirements.

## D. Idempotency

What happens if the same HTTP request is retried?

What happens if a queue delivers the same task more than once?

Consider:
- Idempotency keys.
- Unique constraints.
- Task deduplication.
- Safe retry semantics.
- Preventing duplicate reports and agent executions.

## E. State transitions

Define valid transitions for:

```text
queued
running
completed
failed
```

Consider:
- Duplicate worker delivery.
- Process crashes.
- Stale `running` jobs.
- Retryable versus permanent errors.
- Job timeouts.
- Cancellation.
- Progress updates.

## F. Concurrency and resource limits

What happens if 100 research jobs arrive simultaneously?

Consider:
- Worker concurrency.
- External API rate limits.
- LLM provider quotas.
- Database connection pooling.
- Backpressure.
- Queue depth.
- Per-user limits.

## G. Observability

Use the existing `agent_runs` table as a starting point.

Consider:
- Stage-level status.
- Execution durations.
- Token usage.
- Estimated LLM costs.
- Error classification.
- Retry counts.
- Correlation between jobs and agent runs.

Do not add unnecessary observability infrastructure before the basic workflow is working.

---

# 16. Intended Research Agent Architecture

The planned research workflow includes the following logical components.

### Planner Agent

Breaks the research question into research tasks and decides which information is needed.

### Financial Data Agent

Retrieves company fundamentals and financial metrics.

### SEC / Annual Report Agent

Collects primary-source documents, extracts relevant information, and records document provenance.

### News Research Agent

Collects relevant news and identifies events that may influence the company's prospects.

### RAG Agent

Retrieves relevant document chunks and evidence from PostgreSQL + pgvector.

### Valuation Agent

Uses financial data and explicit assumptions to estimate valuation metrics or scenarios.

### Risk Analysis Agent

Identifies financial, business, market, and execution risks.

### Verification Stage

Checks important claims against retrieved evidence and flags unsupported statements.

### Synthesis Stage

Combines research outputs into a structured final report.

These are planned responsibilities. The agent implementations, external integrations, and LangGraph orchestration have not yet been established as working components.

A central design goal is evidence traceability: important report claims should link back to source material, not merely present unsupported LLM-generated assertions.

---

# 17. Long-Term Architecture

The intended system has three main layers.

## User-facing layer

Streamlit frontend:
- Submit research questions.
- View job progress.
- Browse completed reports.
- Inspect sources and evidence.
- View financial metrics and risk summaries.

## Application and orchestration layer

FastAPI:
- Authentication.
- Request validation.
- Research-job management.
- Report retrieval.
- Status endpoints.

Background workers and LangGraph:
- Research workflow execution.
- Agent coordination.
- Retry and error handling.
- Progress tracking.
- Report generation.

## Data layer

PostgreSQL + pgvector:
- Users.
- Research jobs.
- Agent execution records.
- Documents and chunks.
- Evidence and claims.
- Financial snapshots.
- Reports.

External services:
- Financial data.
- SEC filings and documents.
- News sources.
- LLM/embedding providers.

Deployment may eventually use Docker and AWS. Final deployment architecture should be selected only after the local research pipeline is reliable.

---

# 18. Suggested API Evolution

The existing API surface should be extended deliberately.

Current:

```http
GET /health
POST /api/v1/research
GET /api/v1/research/{job_id}
```

Likely future endpoints:

```http
GET /api/v1/research/{job_id}/status
GET /api/v1/research/{job_id}/report
GET /api/v1/research/{job_id}/evidence
GET /api/v1/research
```

The separate status endpoint may be unnecessary if the main GET endpoint already returns sufficient lifecycle information. Make that decision based on the frontend's requirements rather than creating endpoints automatically.

When asynchronous execution is implemented, consider changing successful job submission from `201 Created` to `202 Accepted` if the semantics accurately represent accepted, not completed, processing.

Document that contract change and update tests accordingly.

---

# 19. Known Technical Decisions and Lessons

1. **UUIDs** are used for entity identifiers.
2. **PostgreSQL** is the authoritative relational store.
3. **pgvector** provides vector storage alongside relational data.
4. **Alembic** manages schema evolution.
5. **Pydantic** validates API requests and response contracts.
6. **Repositories** isolate persistence operations.
7. **Services** coordinate application behavior.
8. **FastAPI dependency injection** supplies request-scoped dependencies.
9. **Transactions must be explicit.** A flush is not a commit.
10. **Integration tests are essential.** They caught the API persistence bug.
11. **Timezone-aware timestamps** are preferred.
12. **Embedding dimensions are a schema constraint.** The current dimension is 768.
13. **The development identity is not production authentication.**
14. **A UUID is not an authorization mechanism.** Resource ownership must be checked.
15. **Background workers must not rely on in-memory state as the only record of a job.**

These decisions should be revisited when requirements change, not treated as universally correct rules.

---

# 20. Instructions for the Next ChatGPT Session

Continue as the technical partner for FinResearch AI.

Follow these rules:

1. Start by verifying the current filesystem, Git status, latest commit, and test suite.
2. Do not assume the Phase 2 commit happened.
3. Do not rewrite working modules without a concrete reason.
4. Preserve the established layered architecture.
5. Work in small, testable increments.
6. Provide exact file paths and code changes.
7. Give commands that can be copied directly into the project's virtual environment.
8. Explain the reason for each important code change.
9. Teach architecture and trade-offs alongside implementation.
10. Ask me to design solutions before revealing yours when that improves interview preparation.
11. Keep cost minimization and performance in balance.
12. Avoid implementing the entire research system at once.
13. Run tests after each meaningful change.
14. Distinguish implemented behavior from proposed architecture.
15. Keep phase tracking explicit and only mark milestones complete when verified.

## Immediate next actions

1. Verify Git status and commit history.
2. Run the full regression suite.
3. Commit the Phase 2 work if it is still uncommitted.
4. Begin Phase 3 with an architecture discussion about asynchronous job processing.
5. Compare execution options and select an approach before implementing workers.
6. Build the smallest reliable end-to-end background job workflow.
7. Add tests for persistence, task dispatch, lifecycle transitions, and failures before building the research agents.

## The first question for Phase 3

Before I give you a design, ask me:

**"A research request may take several minutes. How would you design the system so the HTTP request returns quickly, the job survives application restarts, and the worker can recover from failures?"**

Let me propose a design, challenge my assumptions, and then help me implement it.

The objective is to build FinResearch AI and make me capable of defending the architecture from first principles in a technical interview.
