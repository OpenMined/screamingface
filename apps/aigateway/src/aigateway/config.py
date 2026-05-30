from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    host: str = "127.0.0.1"
    port: int = 9105
    log_level: str = "info"
    database_url: SecretStr = Field(
        default=SecretStr("sqlite://./aigateway.sqlite3"),
        validation_alias="AIGATEWAY_DATABASE_URL",
    )
    jwt_secret: SecretStr | None = Field(default=None, validation_alias="AIGATEWAY_JWT_SECRET")
    admin_password: SecretStr | None = Field(
        default=None, validation_alias="AIGATEWAY_ADMIN_PASSWORD"
    )
    provisioning_token: SecretStr | None = Field(
        default=None, validation_alias="AIGATEWAY_PROVISIONING_TOKEN"
    )
    auth_enabled: bool = Field(default=True, validation_alias="AIGATEWAY_AUTH_ENABLED")
    jwt_ttl_seconds: int = Field(default=86_400, validation_alias="AIGATEWAY_JWT_TTL_SECONDS")
    public_url: str | None = Field(default=None, validation_alias="AIGATEWAY_PUBLIC_URL")

    retry_max_attempts: int = Field(default=3, validation_alias="AIGW_RETRY_MAX_ATTEMPTS")
    retry_backoff_base_seconds: float = Field(
        default=0.5, validation_alias="AIGW_RETRY_BACKOFF_BASE"
    )
    retry_backoff_max_seconds: float = Field(default=8.0, validation_alias="AIGW_RETRY_BACKOFF_MAX")
    retry_max_total_wait_seconds: float = Field(
        default=30.0, validation_alias="AIGW_RETRY_MAX_WAIT"
    )
    retry_jitter_seconds: float = Field(default=0.25, validation_alias="AIGW_RETRY_JITTER")
    provider_max_concurrency: int = Field(
        default=4, validation_alias="AIGW_PROVIDER_MAX_CONCURRENCY"
    )
    # Per-provider overrides to the global cap. Gemini Code Assist's
    # per-account quota is so tight (~1 concurrent req) that the default of 4
    # still 429s on collection fan-outs — set ``{"gemini": 1}`` here while
    # leaving claude/codex at the global default. JSON-parsed from the env var.
    provider_max_concurrency_overrides: dict[str, int] = Field(
        default_factory=dict,
        validation_alias="AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES",
    )

    @field_validator("jwt_secret", "provisioning_token")
    @classmethod
    def _validate_secret_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        if len(value.get_secret_value()) < 32:
            raise ValueError("secret must be at least 32 characters")
        return value

    @field_validator("admin_password")
    @classmethod
    def _validate_admin_password(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        size = len(value.get_secret_value().encode("utf-8"))
        if not 8 <= size <= 72:
            raise ValueError("password must be 8-72 UTF-8 bytes")
        return value

    @field_validator("public_url")
    @classmethod
    def _validate_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("public_url must be an absolute http(s) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("public_url must not include query or fragment")
        return normalized
