"""codex-backend-api plugin — direct OpenAI Responses API implementation.

Most behavior lives in :class:`backend_api_base.BackendApiPluginBase`.
This module declares Codex-specific overrides only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.backend_api_base import (
    BackendApiPluginBase,
    BackendApiSettingsBase,
)
from screamingface.plugins.codex_backend_api.routes import create_route_bundle, create_router

if TYPE_CHECKING:
    from fastapi import FastAPI


class CodexBackendApiSettings(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_CODEX_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description=("Default OpenAI model. Falls back to 'o4-mini' if still unset at call time."),
    )
    connection_id: str | None = Field(
        default=None,
        description=(
            "aigateway OAuthConnection id. When set, tokens are fetched from aigateway "
            "instead of ~/.codex/auth.json."
        ),
    )
    aigw_url: str = Field(
        default="http://localhost:9105",
        description="Base URL of the aigateway service.",
    )


def _maybe_aigw_source(settings: CodexBackendApiSettings, app: FastAPI | None = None):
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


class CodexBackendApiPlugin(BackendApiPluginBase):
    name = "codex-backend-api"
    description = (
        "Direct OpenAI Chat Completions API backend -- reads OAuth token "
        "from the Codex CLI credential store (~/.codex/auth.json). "
        "Same route shapes as claude-backend-api but at /codex/* prefix."
    )
    tags: list[str] = ["product:openai"]
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = ["aigw-codex-backend"]
    backend_call_paths: list[str] = ["/codex"]
    cli_auth_command = "codex auth login"
    backend_status_help = {
        "rate_limited": "OpenAI API rate limit reached. Capacity will reset automatically.",
        "reauth": (
            "Codex OAuth token is missing, expired, or the refresh token was already used. "
            "Click Re-authenticate to run 'codex auth login'."
        ),
        "degraded": "Codex backend is available but experiencing issues.",
    }
    settings_class = CodexBackendApiSettings

    schema_link_base = "/codex/"
    create_route_bundle = staticmethod(create_route_bundle)
    create_router = staticmethod(create_router)

    def customize_schema(self, schema: dict) -> dict:
        schema = super().customize_schema(schema)
        props = schema.get("properties", {})
        if "connection_id" in props:
            props["connection_id"]["x-aigw-connection-picker"] = {
                "provider": "codex",
                "aigw_url_field": "aigw_url",
            }
        return schema

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.codex_backend_api.backend import OpenAIBackend
        from screamingface.plugins.codex_backend_api.interpreter import (
            CodexBackendApiInterpreter,
        )

        settings: CodexBackendApiSettings = self.settings  # type: ignore[assignment]
        aigw_source = _maybe_aigw_source(settings, app)
        backend = OpenAIBackend(aigw_source=aigw_source)

        return CodexBackendApiInterpreter(
            app=app,
            settings=settings,
            backend=backend,
        )
