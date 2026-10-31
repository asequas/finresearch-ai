"""API shapes for the research agent's trace and the analyst chat (ADR 0008)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ToolCallOut(BaseModel):
    tool: str
    input: dict
    summary: str
    ms: int


class PlannedQuestionOut(BaseModel):
    id: str
    question: str
    focus: str
    approach: str


class ResearcherOut(BaseModel):
    task_id: str
    kind: str  # "question" (from the plan) or "gap" (sent back by the critic)
    question: str
    round: int
    status: str
    attempt: int
    started_at: datetime
    duration_ms: int | None
    answer: str | None
    notes: int | None
    gaps: list[str] = []
    dropped_handles: list[str] = []
    tool_calls: list[ToolCallOut] = []
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    error_message: str | None


class RoundOut(BaseModel):
    revision: int
    restored: bool = False  # a re-check after putting back an earlier, better-verified draft
    verdicts: dict[str, int] = {}
    decision: str | None = None  # the critic's: "revise", "restore" or "finish"
    reason: str | None = None
    gaps: list[dict] = []


class TraceTotals(BaseModel):
    researchers: int
    tool_calls: int
    revisions: int
    input_tokens: int
    output_tokens: int


class AgentTraceResponse(BaseModel):
    job_id: uuid.UUID
    mode: str  # "agent", "linear" (older jobs) or "pending" (not started)
    plan: list[PlannedQuestionOut] = []
    researchers: list[ResearcherOut] = []
    rounds: list[RoundOut] = []
    totals: TraceTotals


class ChatQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class ChatCitationOut(BaseModel):
    handle: str
    quote: str
    verified: bool
    section: str | None = None
    form: str | None = None
    period: str | None = None
    url: str | None = None


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[ChatCitationOut] = []
    tool_steps: list[ToolCallOut] = []
    model: str | None
    created_at: datetime


class ChatThreadResponse(BaseModel):
    job_id: uuid.UUID
    messages: list[ChatMessageOut]
    turns_left: int
    suggestions: list[str] = []
