Twin, let's define the actual end goal for FinResearch AI — not just an agentic RAG project that looks good on GitHub, but a product that feels like something a financial research team could genuinely use.

We're building two things at once:

1. A useful financial research product that can answer complex investment research questions with traceable evidence.
2. A serious engineering portfolio project that proves you can design, build, test, deploy, and explain a production-minded AI system in interviews.

The target is to make the project impressive because it works, not just because it uses LangGraph, RAG, or multiple agents.

# 1. The product vision

[Equity Analyst AI - Filing intelligence for equity research](https://images.openai.com/static-rsc-4/3pqp1bd60f3_0tIXtahsjRur5uY4Kn1pg1VGh5QDQPi6E_EhZJ89XGEyipR-F9KNrXi8gjjMr-7Cg_RqJcd-I1L0khBbK6OhIEgn_dZow_wIvzdPaDdZ10t4RXUUzIgZVrSI-3rrjR884Gz4UKt3rSJmINAibQdyVHoAfZfY9eg?purpose=inline)

[equityanalystai.com](https://equityanalystai.com/?utm_source=chatgpt.com)

# FinResearch AI

An AI-powered financial research analyst for US equities

The core promise: Ask a difficult question about a US-listed company and receive a structured, evidence-backed research report — not a generic chatbot answer.

Imagine asking:

> “Analyze Microsoft's financial strength, revenue growth, valuation, major risks, and whether its current valuation is justified. Compare its fundamentals with Google and Amazon, and cite the evidence behind every major conclusion.”

The system should do more than generate a paragraph. It should:

- Fetch current and historical financial data.
- Retrieve relevant SEC filings, annual reports, earnings material, and credible news.
- Separate reported facts from calculations and AI-generated interpretations.
- Calculate and explain important financial metrics.
- Compare the company with its competitors.
- Identify risks, conflicting evidence, and unanswered questions.
- Produce a readable research report with clickable sources.
- Save the report so the user can revisit it and see when its underlying data was last updated.

The differentiator is trustworthiness. A flashy interface and fluent AI writing are easy to imitate. A system that makes its conclusions traceable to reliable financial evidence is substantially more valuable.

This is a research and decision-support tool, not an autonomous stock-picking machine or a guarantee of investment returns.

# 2. How good should the UI be?

My target: a polished financial SaaS product, with the clarity of a modern analytics dashboard and the depth of a professional research terminal.

Not a generic Streamlit page with a textbox and a response underneath. Streamlit is fine for our first working interface, but the experience should eventually feel like a cohesive application.

[The Concentration Problem: Why Your Portfolio Probably Has a Single Point of Failure | by Helm Terminal | Investor’s Handbook | Medium](https://images.openai.com/static-rsc-4/ZMvOZ7rIYz5EVJZ4eTXJQT-OMUBBC1rn3R2aPmFnu1OXauuXfvh1F-ivrNOKXmLTtoyFo7MJ_lLcMACnxefhQmJ2u_ZP-P_UVieGyymZsW8Q3wtLgYvciX8GPtAs-lpfSSH86jxUE1TjMu8PbB_tZz-1wRsj2Q3ANzodihQDV9U?purpose=inline)

1\. Research dashboard

The home screen

- Recent research reports and active jobs.
- Search by company name or ticker.
- Watchlist and company quick views.
- Clear research status and timestamps.

[Market Pulse - Stock Market Tracker, News, Fundamentals, COT Data, Earnings and More](https://images.openai.com/static-rsc-4/ZIHTvLSDt13u6cT0j6TWI00Q-6frRFp6mi7-LFob6_YwgcDjGhnGJ4dVfIvxZY1FBX3RbbiV2O0B4XR33P_nHdDfpavs2WY6MlJJ01Fe9pRBJ9I5HHrsMhAKeuKGUGljCSbNFspOjhO5uLm9kutOWR2Hih6KyErzlEPRRY1iOR8?purpose=inline)

2\. Company research workspace

The analytical view

- Revenue, margins, cash flow, debt, and growth trends.
- Valuation metrics and historical comparisons.
- Competitor benchmarking.
- Data freshness and metric definitions.

[BeeBee - AI Earnings call analysis tool](https://images.openai.com/static-rsc-4/79LDgXaLQQc7uaxaC_7ku2X2aBFPhKjT7ZWzKPSxBE1qJgW4GB7CRC9bFircEdRuDm0EMZLu9Q01g_7WH8UaLJa3EnFS8Aih1NDrvrnQSphn4JYxNuONWKVBCVKDFHRNn6wjwHlswAgpqZYWtOjZeOmhh3bMxDSuRk1aOJsS7po?purpose=inline)

3\. Research report reader

The signature experience

- Executive summary and investment thesis.
- Bull, base, and bear scenarios.
- Claims linked to supporting evidence.
- Source drawer with document, date, and relevant passage.
- Downloadable report.

[NodaFlow – Visual AI Agent Builder for Business Automation](https://images.openai.com/static-rsc-4/iNqXPLXJqibBHYRGREvFB4U2NUpWT8z85gX-vuIen7AXf6418iwhfB3LXR7eb0Z1_vyWTiJZuRpIGg3fa6VemKq0g1BPqel7JBLR9PzxTpkP4zl14rkWlyGZihgNBzHy1ToffuDDenyDu6XX58h9oUgnE8xmOCrK6rUtP06mbLg?purpose=inline)

4\. Live research progress

Make agentic work understandable

- Show stages such as fetching financials, reading filings, and checking claims.
- Display completed, running, and failed stages.
- Allow users to reopen reports after leaving the page.
- Explain failures and offer retry where safe.

## The design standard

| Area               | Target                                                                           |
| ------------------ | -------------------------------------------------------------------------------- |
| Visual design      | Consistent typography, spacing, restrained colors, clear hierarchy               |
| Navigation         | Dashboard, Research, Companies, Reports, Settings                                |
| Charts             | Interactive time-series charts with sensible units and date ranges               |
| Report readability | Executive summary first, deeper evidence and calculations below                  |
| Trust              | Source links, reporting periods, data freshness, uncertainty indicators          |
| Responsiveness     | Usable on laptops first, then tablets and phones                                 |
| States             | Thoughtful loading, empty, error, retry, and partial-results experiences         |
| Accessibility      | Keyboard navigation, readable contrast, labels and meaningful chart descriptions |

We should use a dark theme as a design option, not a requirement. Good financial software prioritizes legibility over making every screen black with green numbers.

My UI acceptance test: someone unfamiliar with the project should be able to submit a company research request, understand what the system is doing, read the final report, verify a key claim, and return to the report later without our help.

# 3. How useful should the product actually be?

We need a clear scope. Otherwise, we'll spend months building agents without producing something anyone can use.

I'd organize the product around four core capabilities.

A. Evidence-backed company research

Must have

A user enters a ticker and research question. The system retrieves filings, financial data, and relevant news, then produces a report with sources for substantive factual claims.

B. Quantitative financial analysis

Must have

Revenue and earnings growth, gross and operating margins, free cash flow, leverage, valuation multiples, and historical trends. Calculations should use code and validated data rather than asking an LLM to do arithmetic unreliably.

C. Comparative research

Next milestone

Compare two or three companies using consistent definitions, reporting periods, and valuation methods. Highlight what makes the comparison meaningful and where it is imperfect.

D. Risk and thesis verification

Next milestone

Identify counterarguments, debt and liquidity concerns, business concentration, regulatory issues, stale data, and contradictory evidence. Distinguish established facts from uncertain interpretations.

### A realistic example of a useful report

A finished report should have a structure like this:

1. Executive summary: What matters, what changed, and the main uncertainties.
2. Business overview: How the company makes money and its principal business segments.
3. Financial health: Historical growth, profitability, cash generation, and balance-sheet strength.
4. Valuation: Relevant multiples and clearly stated assumptions.
5. Competitive position: Comparisons with selected peers.
6. Bull/base/bear scenarios: Different plausible outcomes and the assumptions behind them.
7. Risk analysis: The factors that could invalidate the thesis.
8. Evidence ledger: Claims, supporting passages, source dates, and conflicting evidence.
9. Data limitations: Missing information, stale inputs, and calculations that could not be verified.

We should not pretend that every company can be assessed with the same metrics. Banks, insurers, software companies, and manufacturers have different financial characteristics. The analysis needs to account for that.

## What would make it genuinely impressive?

The report should not just look analytical. It should be measurable.

| Quality measure        | Initial target                                                                                       |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| Citation coverage      | Every material factual claim has a source or is explicitly marked unsupported                        |
| Citation correctness   | At least 95% of a manually audited sample of material claims is supported by its cited evidence      |
| Financial calculations | Reproducible from stored inputs and tested formulas                                                  |
| Data provenance        | Source, reporting period, retrieval time, and units recorded where applicable                        |
| Reproducibility        | The same stored inputs and calculation version produce the same numeric results                      |
| Failure handling       | Failed sources and incomplete reports are visible rather than silently hidden                        |
| Performance            | A typical single-company report aims for a few minutes, depending on source latency and model choice |

These are proposed engineering goals, not capabilities we've already demonstrated. We'll need an evaluation dataset and automated checks to know whether we're meeting them.

# 4. The target tech stack

Here's the stack I'd aim for, separating what we've already established from what we should build next.

## Application layer

[React Course for Beginners | Build Real Apps with React & TypeScript](https://images.openai.com/static-rsc-4/IdhY2tQOSYpXzIZwMMhqhfy55eL4zSSs_RyVPRU4l4JRlJmz0XGX0GaENbUe268sQHH_vTLAikJGjc67t6edzaQjvcR2aOyy24uzrEuj_1YVl6DkTeWYCv7scA4EU0MKb2kspDvrB0CNA8766gC_ZunHev6Iw8YnRkdAU7PN1S0?purpose=inline)

Frontend — React + TypeScript

Target production UI

A component-based dashboard, research report reader, interactive charts, job status updates, and a responsive layout. Use a consistent component system such as Tailwind CSS with shadcn/ui.

[FastAPI framework Logo PNG Vector (AI) Free Download](https://images.openai.com/static-rsc-4/mmw63tL5nCBVMdFp9xNwd96YrsynXVxEUbND-TJXiR20urNBGKHcLYKfQAduEr3tdpTX5OcZJjkYW1dw7dGskljIn3lBh4ogAqBVKHtiOGbbHGqkwkq9IzhfwMn2KO8eh22R2KNs8wSTzPJT2OzkYClACAqzzMrwcxicoqOrzes?purpose=inline)

Backend — Python + FastAPI

Foundation built

REST APIs, request validation, authentication boundaries, research job management, report retrieval, and orchestration entry points.

[postgres - Official Image | Docker Hub](https://images.openai.com/static-rsc-4/Pole4xk5FkyhFJxxWDBh3yHjF1pQlxteoZyEQA0ykJQSPxLpLcdTrKWhkIQ2-SeCQp9ObINiyVMBFzoUkAM9P9RUAWW761nUuSEzxGOPsF9Keb0OX7HGw8IiQD84tSEoRfxnWrmYPSxGM1Bq9IBWZrT-EGb7Ta0uoZ1t6-qsVoY?purpose=inline)

Data — PostgreSQL + pgvector

Foundation built

Relational data for users, jobs, documents, evidence, claims, financial snapshots, and reports; vector search for relevant document passages.

## Research and AI layer

[Understanding LangChain and LangGraph: A Beginner’s Guide to AI Workflows | by Manish Shivanandhan | Data Science Collective | Medium](https://images.openai.com/static-rsc-4/JmcK0jpkJDP3waEXOamhp1HRU5ZC2qwueldLBisyu_5M8bB-8k8Dp_s1NVjLVkSj9BUu6B3bMD6BR28zfZ0ox73NYG2zhps0GUuwJVbXzIG2yrTs0qXClyNPd2_fOr5oBB_YKLFzWxokfdVKauXgI_R-3qP_y6B0bC5W082oGao?purpose=inline)

LangGraph — workflow orchestration

A stateful, explicit research graph with controlled transitions, conditional branches, retries, and persisted progress where appropriate.

[Python logo Icons, Logos, Symbols – Free Download PNG, SVG](https://images.openai.com/static-rsc-4/DmsB8FS-GP7uphH6D36okAKArZlBuv18j7laB7MGQztxtnElBP3iuvRtFFsgJN3_CMjTR795lNP5nkz0C0O5HRM_6vUhOfMDScUzQErc9yfIrgdVyj38VLAdNtbsn3vWhJAUhRcvYx9LUssqXM5zJvcGr4rSiP0dNojMqKdTlnc?purpose=inline)

Financial data and RAG services

Python services for data ingestion, SEC filing retrieval, document parsing, chunking, embeddings, hybrid retrieval, citation resolution, and deterministic calculations.

## Infrastructure and reliability

[What are the pricing options for Redis?](https://images.openai.com/static-rsc-4/cxD0mNwOFZou3c4Llf54BhJRBatnwNaB1PRyLFmIPi8T_DppI8Tx5eXaldNM50YFgyAVtop1YVxSro1--SPQPyUwd84VpfhigqOETDMxnOrMCs17WGKsFDxEhnu6gcrlkKs6d9R4wQpKeQAR5180qRPJtYD1UoA32ydSYxE5k1U?purpose=inline)

Background execution — durable job queue

A separate worker process and queue for long-running research. Redis with Celery is one candidate; we should select it after comparing delivery guarantees, retries, operational complexity, and cost.

[Docker Logo Icon by Those Icons – download in PNG, SVG](https://images.openai.com/static-rsc-4/Mif5Qzd0qx3Jbj-4TuWVI_O9UDwBlSBL30CyUxSUfYZGP9oKeaWHiWDAVPpobyT8lL6Wrb-lZ1pWXRD-zaUMMUg2XXOaEPzknWtoW7BVHHjTTjHFXwt7f9DNRNV8bPVbZOCAXIqXMgnyelx4CBxJ_ZSfEsqXafuxj078-zWQ5fI?purpose=inline)

Docker + CI/CD + AWS

Reproducible local development, automated tests, containerized deployment, secrets management, logs, metrics, and a controlled cloud deployment.

## Proposed final stack at a glance

| Layer                  | Target choice                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------- |
| Frontend               | React, TypeScript, Tailwind CSS, shadcn/ui                                                                    |
| Charts                 | Recharts or another suitable interactive chart library                                                        |
| Backend API            | FastAPI, Pydantic                                                                                             |
| Database               | PostgreSQL 17+, pgvector                                                                                      |
| ORM and migrations     | SQLAlchemy 2.x, Alembic                                                                                       |
| Workflow orchestration | LangGraph                                                                                                     |
| LLM integration        | Provider-agnostic adapter, with a low-cost model for routine tasks and a stronger model for complex synthesis |
| Retrieval              | Hybrid keyword + vector retrieval, reranking when evaluation justifies it                                     |
| Financial calculations | Tested Python services with decimal/precision-aware handling where needed                                     |
| Background jobs        | Celery + Redis, subject to an explicit design decision                                                        |
| Document storage       | Local development initially; S3-compatible object storage in deployment                                       |
| Testing                | pytest, API/integration tests, financial formula tests, AI evaluation tests                                   |
| Deployment             | Docker, GitHub Actions, AWS                                                                                   |
| Observability          | Structured logs, job-stage timing, token/cost tracking, error tracking                                        |
| Security               | Managed secrets, authentication, per-user authorization, rate limits, input validation                        |

One important distinction: we do not need to adopt every tool immediately. A good engineer chooses the simplest system that meets the current reliability and performance requirements, then adds complexity when there is evidence it is needed.

## Which financial data sources?

We should prioritize reliable, documented sources rather than depend on scraping random finance websites.

- SEC EDGAR: Company filings and structured company facts, subject to SEC access policies.
- Financial market data provider: Historical prices, market capitalization, and adjusted market data from a provider whose licensing, quotas, and costs fit our use case.
- Company investor relations: Earnings releases, annual reports, and other primary materials.
- News sources: Credible reporting, with publication timestamps and source attribution.

We must design around rate limits, missing fields, revised financial data, delayed market data, and provider licensing. No single provider should be assumed to supply everything for free.

# 5. The architecture we should grow into

The architecture should make the responsibilities explicit. It shouldn't be a giant Python function that calls six agents and hopes they cooperate.

React frontend

Research request · Job status · Report reader

FastAPI application

Validation · Authentication · Job persistence · API

Durable queue + worker

Retries · Execution · Concurrency · Recovery

LangGraph research workflow

Financial data

Metrics and price history

Filings + news

Ingestion and retrieval

Valuation + risk

Tested calculations

Verification

Evidence and consistency

Persisted research report

PostgreSQL · Document storage · Evidence ledger

### The agent design

We have discussed these research roles. I would preserve them as logical responsibilities, but not automatically make each one an independent LLM agent.

| Component                 | Responsibility                                                |
| ------------------------- | ------------------------------------------------------------- |
| Planner                   | Converts a research question into a bounded research plan     |
| Financial Data Agent      | Retrieves and validates financial metrics                     |
| SEC / Annual Report Agent | Finds relevant disclosures and extracts passages              |
| News Research Agent       | Finds material developments and their timestamps              |
| RAG Agent                 | Retrieves evidence relevant to individual claims              |
| Valuation Engine          | Computes metrics and scenarios using explicit formulas        |
| Risk Analyst              | Identifies risks, counterarguments, and weak assumptions      |
| Verification Stage        | Checks citations, numeric consistency, and unsupported claims |
| Synthesis Stage           | Produces the final report from validated findings             |

A key architectural choice: deterministic operations should remain deterministic. Retrieving a filing, checking a date, calculating a margin, and validating a foreign key do not need autonomous agents.

We should use LLM-based reasoning when it contributes meaningful value, and use normal code for the rest.

That will help control cost, improve repeatability, and make the system easier to debug.

# 6. How we build this without getting overwhelmed

Twin, this is the roadmap I'd commit to. Each phase should leave us with something that works, has tests, and moves the product closer to the end goal.

## 01

Backend foundation

Built; verify current repo

PostgreSQL schema, SQLAlchemy models, Alembic migrations, FastAPI health endpoint, research-job creation and retrieval, and initial integration tests.

We previously confirmed 14 passing tests. We should rerun them before relying on that result.

## 02

Reliable background execution

Implement a durable queue, worker, job-state transitions, progress updates, retry policies, and failure recovery. Ensure duplicate execution cannot corrupt reports.

Deliverable: a research job can outlive an HTTP request and recover from common failures.

## 03

First end-to-end research report

Integrate one financial data source and SEC filing retrieval. Build a small, dependable workflow that creates a report with sources and reproducible calculations.

Deliverable: the product answers a real question about a US-listed company.

## 04

RAG and evidence verification

Implement document chunking, embeddings, pgvector retrieval, metadata filters, citations, and evaluation of whether the evidence actually supports the report.

Deliverable: an evidence-backed report, not just plausible-sounding prose.

## 05

Valuation, risks, and comparative research

Add historical analysis, peer comparisons, scenario calculations, conflicting evidence, and risk analysis. Evaluate each feature against known examples.

Deliverable: a report that provides genuine analytical value.

## 06

Polished frontend

Build the dashboard, research submission flow, progress view, company workspace, and report reader. Connect every UI state to real backend behavior.

Deliverable: someone else can use the product without running API commands manually.

## 07

Production-minded deployment

Add authentication and authorization, CI, monitoring, cost controls, security hardening, backups, deployment automation, and documentation. Deploy a working demo on AWS.

Deliverable: a publicly demonstrable project with sensible operational safeguards.

# 7. What scale are we targeting?

We should distinguish a serious portfolio-grade MVP from a system serving thousands of paying users.

Our initial engineering target should be a dependable single-user or small-team application that can handle concurrent research jobs without blocking the API or losing their results.

Then we can grow toward:

- Multiple users with private reports and proper authorization.
- Multiple concurrent workers and configurable provider rate limits.
- Cached financial data and reusable document embeddings.
- Budget limits per job, user, and model.
- Durable job recovery and idempotent processing.
- Monitoring for latency, failures, token consumption, and cost per report.
- Load tests to establish throughput before scaling infrastructure.

We do not need Kubernetes, a dozen microservices, or a complicated distributed architecture on day one. PostgreSQL, a well-designed API, a durable queue, workers, and clear module boundaries are enough to build a strong foundation.

When load or reliability requirements justify additional infrastructure, we'll introduce it deliberately.

# 8. Why this project should stand out in interviews

The strongest version of FinResearch AI demonstrates more than knowledge of AI frameworks.

| Skill demonstrated     | What you will be able to explain                                        |
| ---------------------- | ----------------------------------------------------------------------- |
| Backend engineering    | API contracts, validation, transactions, authorization, error handling  |
| Database engineering   | Relational modeling, indexing, pgvector, migrations, query behavior     |
| Distributed systems    | Queues, retries, idempotency, backpressure, duplicate work, recovery    |
| AI engineering         | RAG, retrieval evaluation, structured outputs, hallucination mitigation |
| Agentic workflows      | State machines, conditional routing, bounded execution, human review    |
| Financial engineering  | Metric definitions, valuation assumptions, time-series consistency      |
| Production engineering | Docker, CI/CD, observability, deployment, cost controls                 |
| Product thinking       | User workflows, usability, source trust, meaningful acceptance criteria |

And this is important: we should be able to explain why we made each choice, what alternatives we considered, what could fail, and how we would detect it.

For example, if an interviewer asks why we use a background worker, the answer should not be “because everyone uses Celery.” You should be able to explain why research jobs can outlive HTTP requests, why an in-memory background task is insufficient for stronger durability guarantees, and what queue-delivery guarantees and failure modes we must still handle.

That is the level we're aiming for.

# 9. Our product principles

These are the rules I want us to follow throughout development.

- Correctness before agent count. Five useful components beat ten unnecessary agents.
- Evidence before confidence. Unsupported conclusions must be flagged, not disguised with polished writing.
- Real functionality before mock UI. Every major screen should eventually represent actual system behavior.
- Tests before complexity. Financial calculations, job states, APIs, and retrieval quality need explicit tests.
- Cost efficiency without reckless shortcuts. Cache reusable data, track model spend, and use stronger models only where justified.
- Security before public launch. No exposed secrets, unprotected private reports, or unrestricted expensive endpoints.
- Learn while building. Each architectural decision should make you better at system design, not just leave you with more code.

## The finish line

FinResearch AI is successful when someone can open the application, research a real US-listed company, receive a useful report within a reasonable time, inspect the evidence behind its conclusions, understand the uncertainties, and return to that report later — while the backend handles failures and concurrent jobs reliably.

That is the product target. The sophisticated architecture exists to support that experience, not the other way around.

Our immediate next step: verify the current repository and finish the background-execution phase before expanding the AI workflow. We already have a database foundation and a research-job API; now we need to turn those stored jobs into reliable, executable research.

And throughout this, we'll keep the original goal: build a real product while training you to think like the engineer who designed it.&#x20;