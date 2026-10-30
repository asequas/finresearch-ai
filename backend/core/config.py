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
    pipeline: str = "research"  # "research" or "stub" (Phase 3 stub stages)
    gemini_api_key: str | None = None
    gemini_fast_model: str = "gemini-3.5-flash-lite"
    # Pro models have no free-tier quota; a thinking Flash model drafts and synthesizes.
    gemini_strong_model: str = "gemini-3.6-flash"
    # Tried in order when the preferred model is overloaded (503) or out of quota (429).
    gemini_strong_fallbacks: list[str] = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.7-flash"]
    gemini_fast_fallbacks: list[str] = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_timeout_seconds: int = 180
    # Free tier: 100 embedding requests per minute, and every text in a batch counts as one request.
    gemini_embed_per_minute: int = 90
    sec_user_agent: str | None = None
    data_cache_dir: str = ".cache/finresearch"

    # API
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
