from functools import lru_cache

from pydantic import Field, SecretStr
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
    ai_allowed_providers: str = "local,gateway"
    ai_story_summary_primary_model: str = "local:story-summary-v1"
    ai_story_summary_fallback_models: str = ""
    ai_story_summary_max_cost: float = Field(default=0.02, ge=0, le=100)
    ai_story_summary_max_input_tokens: int = Field(default=4000, ge=128, le=100000)
    ai_story_summary_max_output_tokens: int = Field(default=300, ge=32, le=10000)
    ai_story_summary_max_retries: int = Field(default=2, ge=0, le=5)
    ai_query_primary_model: str = "local:grounded-answer-v1"
    ai_query_fallback_models: str = ""
    ai_query_max_cost: float = Field(default=0.03, ge=0, le=100)
    ai_query_max_input_tokens: int = Field(default=6000, ge=128, le=100000)
    ai_query_max_output_tokens: int = Field(default=500, ge=32, le=10000)
    ai_query_max_retries: int = Field(default=2, ge=0, le=5)
    ai_rate_limit: int = Field(default=20, ge=0, le=10000)
    ai_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86400)
    ai_provider_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    ai_cache_ttl_seconds: int = Field(default=86400, ge=60, le=2592000)
    ai_gateway_url: str | None = None
    ai_gateway_api_key: SecretStr | None = None
    ai_gateway_name: str = "external-gateway"
    ai_local_stub_response_mode: str = Field(
        default="success", pattern="^(success|malformed|provider_error|rate_limit|timeout)$"
    )
    notification_worker_enabled: bool = True
    notification_worker_poll_seconds: int = Field(default=5, ge=1, le=3600)
    notification_worker_batch_size: int = Field(default=100, ge=1, le=1000)
    notification_gateway_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    notification_email_gateway_url: str | None = None
    notification_email_gateway_key: SecretStr | None = None
    notification_web_push_gateway_url: str | None = None
    notification_web_push_gateway_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
