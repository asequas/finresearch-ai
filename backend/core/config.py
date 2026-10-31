from decimal import Decimal
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    # Worker / queue (ADR 0001)
    worker_lease_seconds: int = 60
    worker_poll_interval_seconds: float = 1.0
    job_max_attempts: int = 5
    job_retry_base_seconds: int = 15
    # Provider overloads (429/5xx) last minutes: 60s, 120s, 240s… capped at 10 minutes.
    job_busy_retry_base_seconds: int = 60

    # Research pipeline
    pipeline: str = "research"  # "research" (agent, ADR 0008), "linear" (ADR 0006 baseline) or "stub"
    gemini_api_key: str | None = None
    gemini_fast_model: str = "gemini-3.5-flash-lite"
    # Pro models have no free-tier quota; a thinking Flash model drafts and synthesizes.
    gemini_strong_model: str = "gemini-3.6-flash"
    # Tried in order when the preferred model is overloaded (503) or out of quota (429).
    # gemini-flash-latest is deliberately absent: in live runs the alias timed out (504) after ~3 minutes on every
    # call while pinned models answered in seconds. The chain ends with a lite model so a draft always comes back.
    # Only models on Google's price list, so every call can be costed (ADR 0009). 3.8-flash costs the same as 3.6.
    gemini_strong_fallbacks: list[str] = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    gemini_fast_fallbacks: list[str] = ["gemini-3.1-flash-lite"]
    # Drafting and synthesis are structured extraction from supplied evidence; deep thinking only adds latency.
    gemini_thinking_level: str = "low"
    gemini_embedding_model: str = "gemini-embedding-001"
    # Successful drafts take seconds to ~1 minute; a model that will 504 should hand over to the next one sooner.
    gemini_timeout_seconds: int = 90
    # Free tier: 100 embedding requests per minute, and every text in a batch counts as one request.
    gemini_embed_per_minute: int = 90
    # Billing and spend caps (ADR 0009). "free": nothing is billed and caps never block; "paid": Tier 1 or above.
    gemini_billing: Literal["free", "paid"] = "free"
    budget_daily_usd: Decimal = Decimal("1.00")
    budget_monthly_usd: Decimal = Decimal("5.00")
    # Optional requests-per-minute ceilings per model, e.g. {"gemini-3.6-flash": 5}. Empty = no pacing beyond the
    # 1-second spacing; 429s put a model in cool-down either way.
    gemini_model_rpm: dict[str, int] = {}
    # Second-stage retrieval (ADR 0007): "minilm", "jina-turbo" or "none".
    reranker: str = "minilm"
    rerank_candidates: int = 20
    sec_user_agent: str | None = None
    data_cache_dir: str = ".cache/finresearch"

    # Research agent (ADR 0008). Every loop is bounded: these caps are the agent's budget.
    agent_max_researchers: int = 6
    agent_tool_calls_per_researcher: int = 6
    agent_model_calls_per_researcher: int = 8
    agent_max_revisions: int = 1
    # Researchers running at once; the free tier rate-limits harder than a paid key.
    agent_max_concurrency: int = 3
    chat_max_turns: int = 30
    chat_tool_calls: int = 6

    # API
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
