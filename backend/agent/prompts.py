"""Schemas and prompts for the research agent (ADR 0008). Shared rules live in backend.pipeline.prompts."""
from typing import Literal

from pydantic import BaseModel, Field

from backend.pipeline.prompts import DRAFT_PROMPT, SectionName


class PlannedQuestion(BaseModel):
    question: str = Field(description="One focused question a 10-K/10-Q can answer")
    focus: SectionName
    approach: str = Field(description="One line: which filing sections or computed metrics should answer it")


class AgentPlan(BaseModel):
    questions: list[PlannedQuestion] = Field(description="3 to 6 sub-questions, most important first")


class FindingNote(BaseModel):
    text: str = Field(description="One finding, in one sentence, stated only as strongly as the evidence allows")
    passages: list[str] = Field(default_factory=list, description="Passage handles you read, e.g. 'P:1a2b3c4d'")
    metrics: list[str] = Field(default_factory=list, description="Metric handles you used, e.g. 'M4'")


class Findings(BaseModel):
    """Call this when you have researched the question (or run out of useful searches)."""

    answer: str = Field(description="2-3 sentences answering the sub-question from what you found")
    notes: list[FindingNote] = Field(description="2-6 findings, each backed by passages and/or metrics")
    gaps: list[str] = Field(default_factory=list, description="What the filings did not answer")


PLAN_PROMPT = """Research request: "{query}"
Company: {company} ({ticker}), latest annual report period ending {period_end}.

You lead a small research team. Each sub-question you write goes to one researcher who can search the
company's 10-K/10-Q text and look up metrics computed from SEC XBRL. Write {min_q} to {max_q} sub-questions that
together answer the request, most important first. Cover what the user asked before anything else; then
the business model, profitability and cash generation, balance sheet, and the risks that could change the view."""

RESEARCHER_SYSTEM = """You are an equity researcher investigating one question about {company} ({ticker}) using only
its SEC filings and metrics computed by code.

How to work:
- Search the filings with specific terms a filing would use; read a passage in full when the preview is cut off.
- Use get_metrics for any number (margins, growth, cash flow, leverage). Never compute numbers yourself.
- Stop when the question is answered or two searches in a row add nothing. You have at most {tool_calls} tool calls.
- Finish by calling Findings. Every note must cite the passage handles (P:...) and/or metric handles (M...) it rests on.
  Cite only handles that a tool actually returned to you. If the filings don't answer something, list it in gaps."""

RESEARCH_TASK = """Research request from the user: "{query}"
Your sub-question: {question}
Focus: {focus}. Suggested approach: {approach}"""

GAP_TASK = """Research request from the user: "{query}"
A fact-checker rejected this claim from the draft report:
  "{claim}"
Reason: {note}

Find passages or computed metrics that establish, correct or refute it. If the filings don't support it,
say so plainly in gaps; a claim that can't be verified should be dropped, not reworded."""

AGENT_DRAFT_PROMPT = DRAFT_PROMPT + """

## Research notes (from the researchers; their passages are the excerpts above)
{notes}
{feedback}"""

FEEDBACK_BLOCK = """
## Fact-checker feedback on the previous draft
These claims failed verification. Fix them using the excerpts (exact quotes, the metric's displayed value) or drop them:
{items}"""

CriticDecision = Literal["revise", "finish"]
