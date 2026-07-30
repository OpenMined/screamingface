from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AuthMode = Literal["jwt", "gateway_headers", "disabled"]


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
    """LEGACY. Supplies the default for :attr:`auth_mode`; new deployments set the mode directly."""

    auth_mode: AuthMode = Field(default="jwt", validation_alias="AIGW_AUTH_MODE")
    """How the gateway establishes who is calling. The single source of truth in code.

    - ``jwt`` — verify the gateway's own bearer token (the historical behavior).
    - ``gateway_headers`` — trust the identity headers Envoy injects
      (:mod:`aigateway.core.auth.gateway_identity`). Sound ONLY while this port is unreachable
      except through Envoy.
    - ``disabled`` — every caller is anonymous. Loopback-only, enforced by
      :class:`AuthDisabledLocalOnlyMiddleware`.

    WHY a mode rather than a second boolean: with ``auth_enabled`` plus a hypothetical
    ``trust_headers`` flag, "false/false" would mean authenticate-nobody-and-trust-nothing — a
    configuration that reads like the safe one and is in fact the most permissive. Three named
    states make "trust everything" unreachable by accident.
    """
    jwt_ttl_seconds: int = Field(default=86_400, validation_alias="AIGATEWAY_JWT_TTL_SECONDS")
    public_url: str | None = Field(default=None, validation_alias="AIGATEWAY_PUBLIC_URL")

    # Encryption-at-rest for credential_blobs (SF-221). secret_key is the master
    # key for the default `local` AES-GCM provider; when unset in local dev it is
    # auto-generated and persisted in the secret_master_keys table. Multi-worker /
    # hosted deployments MUST set AIGATEWAY_SECRET_KEY so every worker shares one key.
    #
    # Content (base64 + exactly-32-bytes) is intentionally NOT validated here: a
    # field_validator that raises would let Pydantic capture the rejected key in
    # the ValidationError (input_value=), leaking it into startup logs despite the
    # SecretStr type. The single source of truth for key validation is
    # ``secrets.master_key._decode_key``, which runs at startup (in the lifespan,
    # for the providers that actually use the key) and raises a clean RuntimeError
    # that never echoes the value.
    secret_key: SecretStr | None = Field(default=None, validation_alias="AIGATEWAY_SECRET_KEY")
    secret_provider: str = Field(default="local", validation_alias="AIGATEWAY_SECRET_PROVIDER")

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
    # leaving claude/codex at the global default. The key may be the family
    # name (``gemini``) or the full derived provider string (``gemini-cli``);
    # both match. JSON-parsed from the env var.
    provider_max_concurrency_overrides: dict[str, int] = Field(
        default_factory=dict,
        validation_alias="AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES",
    )

    # Opt-in persistent response cache for deterministic chat completions
    # (SF-265). Disabled by default; behavior with the flag off is unchanged.
    request_cache_enabled: bool = Field(
        default=False, validation_alias="AIGW_REQUEST_CACHE_ENABLED"
    )
    request_cache_default_ttl_seconds: int = Field(
        default=600, gt=0, validation_alias="AIGW_REQUEST_CACHE_TTL_SECONDS"
    )
    request_cache_max_ttl_seconds: int = Field(
        default=3600, gt=0, validation_alias="AIGW_REQUEST_CACHE_MAX_TTL_SECONDS"
    )
    request_cache_max_response_bytes: int = Field(
        default=1_000_000, gt=0, validation_alias="AIGW_REQUEST_CACHE_MAX_RESPONSE_BYTES"
    )

    @model_validator(mode="after")
    def _reconcile_auth_mode(self) -> Settings:
        """Derive the mode from the legacy flag, and refuse a configuration that means both.

        An existing deployment sets only ``AIGATEWAY_AUTH_ENABLED``, so that alone must keep
        producing the behavior it always did — ``false`` there means anonymous, i.e. ``disabled``.

        The two settings disagreeing is a hard error rather than a precedence rule: silently
        preferring either one would leave an operator who wrote ``AUTH_ENABLED=false`` alongside
        ``AUTH_MODE=gateway_headers`` believing something about their auth posture that is false.
        """
        explicit_mode = "auth_mode" in self.model_fields_set
        if not explicit_mode:
            if not self.auth_enabled:
                self.auth_mode = "disabled"
            return self
        if not self.auth_enabled and self.auth_mode != "disabled":
            raise ValueError(
                "AIGATEWAY_AUTH_ENABLED=false conflicts with "
                f"AIGW_AUTH_MODE={self.auth_mode!r} — drop AIGATEWAY_AUTH_ENABLED and let "
                "AIGW_AUTH_MODE be the only auth setting"
            )
        return self

    @model_validator(mode="after")
    def _validate_request_cache_ttls(self) -> Settings:
        if self.request_cache_default_ttl_seconds > self.request_cache_max_ttl_seconds:
            raise ValueError("request cache default TTL must not exceed the max TTL")
        return self

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

    @field_validator("secret_provider")
    @classmethod
    def _validate_secret_provider(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"local", "kms"}:
            raise ValueError("AIGATEWAY_SECRET_PROVIDER must be 'local' or 'kms'")
        return normalized
