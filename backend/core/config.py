from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    # Worker / queue (ADR 0001)
    worker_lease_seconds: int = 60
    worker_poll_interval_seconds: float = 1.0
    job_max_attempts: int = 3
    job_retry_base_seconds: int = 15

    # Research pipeline
    pipeline: str = "research"  # "research" or "stub" (Phase 3 stub stages)
    gemini_api_key: str | None = None
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_strong_model: str = "gemini-2.5-pro"
    gemini_embedding_model: str = "gemini-embedding-001"
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
