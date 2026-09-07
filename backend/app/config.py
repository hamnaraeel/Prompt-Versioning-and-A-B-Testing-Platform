from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://ppat:ppat@localhost:5432/ppat"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    default_confidence_level: float = 0.95
    guardrail_error_rate_threshold: float = 0.10
    auto_promote_hold_hours: float = 24.0
    worker_poll_seconds: float = 15.0


settings = Settings()
