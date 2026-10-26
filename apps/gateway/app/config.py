"""ModelRail configuration. All secrets come from the environment only."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", populate_by_name=True)

    app_name: str = "modelrail-gateway"
    environment: str = "local"

    database_url: str = "sqlite:///./modelrail.db"
    redis_url: str | None = None

    # Bootstrap admin identity (hashed in-memory compare; real admins live in DB)
    admin_token: str = "dev-admin-token-change-me"
    api_key_pepper: str = Field(
        default="dev-pepper-change-me",
        validation_alias=AliasChoices("API_KEY_PEPPER", "MODELRAIL_API_KEY_PEPPER"),
    )

    # Providers
    ollama_base_url: str = "http://localhost:11434"
    remote_provider_base_url: str | None = None
    remote_provider_api_key: str | None = None
    remote_provider_model: str = "gpt-4o-mini"
    allow_private_provider_urls: bool = False
    mock_scripted_json: str | None = None  # JSON map for [[script:KEY]] responses

    # Reliability defaults. The long env names are the documented ones from
    # .env.example (spec section 20 workflow); they MUST bind — silently
    # ignored tuning variables are a safety bug, not a cosmetic one.
    provider_connect_timeout_s: float = Field(
        default=3.0,
        validation_alias=AliasChoices("PROVIDER_CONNECT_TIMEOUT_SECONDS", "provider_connect_timeout_s"),
    )
    provider_request_timeout_s: float = Field(
        default=30.0,
        validation_alias=AliasChoices("PROVIDER_REQUEST_TIMEOUT_SECONDS", "provider_request_timeout_s"),
    )
    request_deadline_s: float = Field(
        default=60.0, validation_alias=AliasChoices("OVERALL_REQUEST_DEADLINE_SECONDS", "request_deadline_s")
    )
    #: Total attempt ceiling for one logical request, across retries AND
    #: fallbacks (bound by .env.example's RETRY_MAX_ATTEMPTS).
    max_total_attempts: int = Field(
        default=4, validation_alias=AliasChoices("RETRY_MAX_ATTEMPTS", "max_total_attempts")
    )
    retry_base_delay_s: float = 0.05
    retry_max_delay_s: float = 2.0
    circuit_failure_threshold: int = 5
    circuit_open_s: float = 30.0

    # Governance defaults
    max_request_bytes: int = 256_000
    default_max_output_tokens: int = 1024
    pricing_version: str = Field(
        default="price-v1", validation_alias=AliasChoices("PRICING_VERSION", "pricing_version")
    )
    default_currency: str = Field(
        default="USD", validation_alias=AliasChoices("DEFAULT_CURRENCY", "default_currency")
    )
    stale_reservation_s: int = 600

    # Evaluations
    eval_dataset_path: str = "packages/evals/datasets/modelrail-eval-v1.jsonl"
    eval_package_path: str = "packages/evals"
    evaluation_job_deadline_s: float = Field(
        default=900.0,
        validation_alias=AliasChoices("EVALUATION_JOB_DEADLINE_SECONDS", "evaluation_job_deadline_s"),
    )

    otel_endpoint: str | None = Field(
        default=None, validation_alias=AliasChoices("OTEL_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
