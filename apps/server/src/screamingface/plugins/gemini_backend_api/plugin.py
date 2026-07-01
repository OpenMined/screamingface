"""gemini-backend-api plugin — Google AI Gemini API implementation.

Most behavior lives in :class:`backend_api_base.BackendApiPluginBase`.
This module declares Gemini-specific settings (fallback chain + 429
wait cap) and overrides only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.backend_api_base import (
    BackendApiPluginBase,
    BackendApiSettingsBase,
)
from screamingface.plugins.gemini_backend_api.routes import create_route_bundle, create_router

if TYPE_CHECKING:
    from fastapi import FastAPI


class GeminiBackendApiSettings(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_GEMINI_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description="Default Gemini model. Falls back to 'gemini-2.5-flash'.",
    )
    fallback_models: list[str] = Field(
        default_factory=lambda: ["gemini-2.5-pro", "gemini-2.5-flash-lite"],
        description=(
            "Fallback chain when the configured model returns "
            "QUOTA_EXHAUSTED 429. Each model has its own quota bucket "
            "on Code Assist, so flash → pro → flash-lite usually "
            "self-heals during a single-model burnout. Empty list "
            "disables fallback."
        ),
    )
    max_total_429_wait_seconds: float = Field(
        default=30.0,
        description=(
            "Cap on cumulative sleep across 429 retries within a single "
            "request. Past this budget the backend raises BackendError(429) "
            "instead of continuing to obey provider retry-after, so request-"
            "level timeouts (e.g. 45s in tests) surface a clean error rather "
            "than an httpx ReadTimeout."
        ),
    )
    connection_id: str | None = Field(
        default=None,
        description=(
            "aigateway OAuthConnection id. When set, tokens are fetched from "
            "aigateway instead of ~/.gemini/oauth_creds.json. Note: if "
            "GEMINI_API_KEY or GOOGLE_API_KEY is set, the API-key path still "
            "wins over the aigw path."
        ),
    )
    aigw_url: str = Field(
        default="http://localhost:9105",
        description="Base URL of the aigateway service.",
    )


def _maybe_aigw_source(settings: GeminiBackendApiSettings, app: FastAPI | None = None):
    """Return an AigwTokenSource configured from settings, or None."""
    if not settings.connection_id:
        return None
    from screamingface.plugins.llm_base.aigw_token_source import (
        AigwTokenSource,
        aigw_jwt_provider_for_app,
    )

    return AigwTokenSource(
        connection_id=settings.connection_id,
        aigw_url=settings.aigw_url,
        aigw_jwt_provider=aigw_jwt_provider_for_app(app),
    )


class GeminiBackendApiPlugin(BackendApiPluginBase):
    name = "gemini-backend-api"
    description = "Direct Google AI Gemini API backend for ensemble fan-out"
    tags: list[str] = ["product:gemini"]
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = ["aigw-gemini-backend"]
    backend_call_paths: list[str] = ["/gemini"]
    cli_auth_command = "gemini auth login"
    backend_status_help = {
        "rate_limited": "Gemini API rate limit reached. Capacity will reset automatically.",
        "reauth": (
            "Gemini OAuth token is missing or has insufficient API scopes. "
            "Click Re-authenticate to run 'gemini auth login'."
        ),
        "degraded": "Gemini backend is available but experiencing issues.",
    }
    settings_class = GeminiBackendApiSettings

    schema_link_base = "/gemini/"
    create_route_bundle = staticmethod(create_route_bundle)
    create_router = staticmethod(create_router)

    def customize_schema(self, schema: dict) -> dict:
        schema = super().customize_schema(schema)
        props = schema.get("properties", {})
        if "connection_id" in props:
            props["connection_id"]["x-aigw-connection-picker"] = {
                "provider": "gemini",
                "aigw_url_field": "aigw_url",
            }
        return schema

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.gemini_backend_api.backend import GeminiBackend
        from screamingface.plugins.gemini_backend_api.interpreter import (
            GeminiBackendApiInterpreter,
        )

        settings: GeminiBackendApiSettings = self.settings  # type: ignore[assignment]
        aigw_source = _maybe_aigw_source(settings, app)
        backend = GeminiBackend(aigw_source=aigw_source)

        return GeminiBackendApiInterpreter(
            app=app,
            settings=settings,
            backend=backend,
        )
