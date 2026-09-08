from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = (
        "postgresql+asyncpg://news_platform:news_platform_dev@localhost:5432/news_platform"
    )
    redis_url: str = "redis://localhost:6379/0"
    ingestion_clock_skew_seconds: int = Field(default=300, ge=1, le=3600)
    ingestion_rate_limit: int = Field(default=300, ge=0)
    ingestion_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    editorial_scheduler_enabled: bool = True
    editorial_scheduler_poll_seconds: int = Field(default=10, ge=1, le=3600)
    editorial_scheduler_batch_size: int = Field(default=50, ge=1, le=500)
    feed_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    analytics_event_max_age_days: int = Field(default=7, ge=1, le=90)
    analytics_future_skew_seconds: int = Field(default=300, ge=0, le=3600)
    analytics_worker_enabled: bool = True
    analytics_worker_poll_seconds: int = Field(default=5, ge=1, le=3600)
    analytics_worker_batch_size: int = Field(default=100, ge=1, le=1000)
    auth_session_hours: int = Field(default=168, ge=1, le=8760)
    auth_login_rate_limit: int = Field(default=10, ge=0, le=1000)
    auth_rate_limit_window_seconds: int = Field(default=300, ge=1, le=86400)
    auth_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    community_rate_limit: int = Field(default=30, ge=0, le=10000)
    community_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86400)


@lru_cache
def get_settings() -> Settings:
    return Settings()
