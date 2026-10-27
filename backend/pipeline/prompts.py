"""LLM output schemas and prompts. The model never computes numbers; it cites metric keys."""
from typing import Literal

from pydantic import BaseModel, Field

SECTIONS = ("business", "growth", "profitability", "cash_flow", "balance_sheet", "risks", "outlook")
SectionName = Literal["business", "growth", "profitability", "cash_flow", "balance_sheet", "risks", "outlook"]


class ResearchPlan(BaseModel):
    sub_questions: list[str] = Field(description="4 to 6 focused questions answerable from a 10-K/10-Q")


class EvidenceRef(BaseModel):
    excerpt_id: str = Field(description="The id of an excerpt, e.g. 'E3'")
    quote: str = Field(description="An exact, verbatim sentence or phrase copied from that excerpt")


class DraftClaim(BaseModel):
    section: SectionName
    claim_type: Literal["fact", "calculation", "interpretation"]
    text: str = Field(description="One self-contained sentence")
    metric_refs: list[str] = Field(default_factory=list, description="Metric ids like 'M4' used by this claim")
    evidence: list[EvidenceRef] = Field(default_factory=list)
    importance: int = Field(ge=1, le=3, description="1 to 3; 3 = central to the answer")


class ClaimDraft(BaseModel):
    claims: list[DraftClaim]


class Judgement(BaseModel):
    claim_id: str
    verdict: Literal["supported", "partially_supported", "unsupported"]
    note: str = Field(description="One sentence explaining the verdict")


class Judgements(BaseModel):
    judgements: list[Judgement]


class KeyPoint(BaseModel):
    text: str
    claim_ids: list[str] = Field(description="Claim ids like 'C2' that support this point")


class Assumption(BaseModel):
    driver: str
    assumption: str
    basis: str = Field(description="Which metric or evidence this assumption is anchored to, e.g. 'M3 revenue CAGR'")


class Scenario(BaseModel):
    name: Literal["bull", "base", "bear"]
    summary: str
    assumptions: list[Assumption]


class Risk(BaseModel):
    title: str
    description: str
    severity: Literal["high", "medium", "low"]
    claim_ids: list[str]


class ReportDraft(BaseModel):
    headline: str = Field(description="One line, neutral, no buy/sell language")
    direct_answer: str = Field(description="2-4 sentences answering the user's question from the evidence")
    executive_summary: str = Field(description="One paragraph")
    key_points: list[KeyPoint]
    investment_thesis: str
    scenarios: list[Scenario]
    risks: list[Risk]
    open_questions: list[str] = Field(description="What the filings can't answer; what an analyst should check next")


ANALYST_SYSTEM = (
    "You are a meticulous equity research analyst working only from SEC filings and pre-computed metrics. "
    "Never do arithmetic and never invent numbers: every number you state must come verbatim from a metric "
    "you cite or from a quoted excerpt. Be neutral, precise and concise. This is decision support, not advice."
)

PLAN_PROMPT = """Research request: "{query}"
Company: {company} ({ticker}), latest annual report period ending {period_end}.

Break the request into 4-6 focused sub-questions that a 10-K/10-Q can answer (business model and segments,
growth drivers, profitability, cash generation, balance sheet, key risks, management's outlook), prioritising
what the user actually asked."""

DRAFT_PROMPT = """Research request: "{query}"
Company: {company} ({ticker})

## Computed metrics (deterministic, from SEC XBRL; cite by id)
{metrics}

## Filing excerpts (cite by id; quote verbatim)
{excerpts}

Write 14-22 claims that together answer the request. Rules:
- claim_type "fact": something the filing states. Must include at least one evidence quote copied verbatim.
- claim_type "calculation": a statement about a metric above. Must list the metric id(s) in metric_refs and use
  the metric's displayed value exactly (e.g. "44.6%"). No other numbers.
- claim_type "interpretation": your analytical judgement. Must cite the metrics and/or quotes it relies on.
- Cover every section that the data supports: {sections}.
- Quotes must be exact substrings of a single excerpt (you may join two parts with "..."). Prefer one sentence.
- If the evidence is thin for something important, say so in an interpretation rather than guessing."""

JUDGE_PROMPT = """For each claim, decide whether the cited material supports it.
- supported: the quotes/metrics fully establish the claim.
- partially_supported: the gist is backed but the claim overstates, generalises or adds unbacked detail.
- unsupported: the material doesn't establish the claim.
Judge only against the material shown, not outside knowledge.

{claims}"""

SYNTHESIS_PROMPT = """Research request: "{query}"
Company: {company} ({ticker}). Data as of fiscal period ending {period_end}.

## Verified claims (cite by id)
{claims}

## Key metrics
{metrics}

## Known limitations
{limitations}

Write the report. Rules:
- Use only the claims and metrics above. Every key point must cite claim ids.
- Scenarios: bull/base/bear. Each assumption must be anchored to a metric id or claim id in `basis`.
  No price targets or valuation multiples (market price data is out of scope).
- Risks: 3-6, ordered by severity, each citing claim ids.
- No buy/sell/hold recommendations; describe what the evidence implies and what would change the view."""
