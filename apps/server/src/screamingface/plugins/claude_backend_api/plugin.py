"""claude-backend-api plugin — direct Anthropic Messages API implementation.

Most behavior lives in :class:`backend_api_base.BackendApiPluginBase`.
This module declares Claude-specific overrides only.

Settings mirror the legacy ``claude-backend`` field-for-field. CLI-only
fields (``permission_mode``, ``dangerously_skip_permissions``,
``max_budget_usd``) are accepted for ``sf.json`` compatibility but
silently ignored at request time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.backend_api_base import (
    BackendApiPluginBase,
    BackendApiSettingsBase,
)
from screamingface.plugins.claude_backend_api.routes import create_route_bundle, create_router

if TYPE_CHECKING:
    from fastapi import FastAPI


class ClaudeBackendApiSettings(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description=(
            "Default Claude model. Falls back to 'claude-sonnet-4-6' if still unset at call time."
        ),
    )
    connection_id: str | None = Field(
        default=None,
        description=(
            "aigateway OAuthConnection id. When set, the plugin fetches access tokens "
            "from aigateway instead of reading the Claude Code credential store."
        ),
    )
    aigw_url: str = Field(
        default="http://localhost:9105",
        description="Base URL of the aigateway service.",
    )


def _maybe_aigw_source(settings: ClaudeBackendApiSettings, app: FastAPI | None = None):
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


class ClaudeBackendApiPlugin(BackendApiPluginBase):
    name = "claude-backend-api"
    description = (
        "Direct Anthropic Messages API backend — drop-in replacement for "
        "claude-backend that uses OAuth from the Claude Code credential "
        "store instead of shelling out to the claude CLI. Same routes, "
        "same request/response shapes, same profile config."
    )
    tags: list[str] = ["product:claude"]
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = ["aigw-claude-backend"]
    backend_call_paths: list[str] = ["/claude"]
    cli_auth_command = "claude auth login"
    backend_status_help = {
        "rate_limited": "Claude API rate limit reached. Capacity will reset automatically.",
        "reauth": (
            "Claude OAuth token is missing or expired. "
            "Click Re-authenticate to open a terminal and run 'claude auth login'."
        ),
        "degraded": "Claude backend is available but experiencing issues.",
    }
    settings_class = ClaudeBackendApiSettings

    schema_link_base = "/claude/"
    create_route_bundle = staticmethod(create_route_bundle)
    create_router = staticmethod(create_router)

    def customize_schema(self, schema: dict) -> dict:
        schema = super().customize_schema(schema)
        props = schema.get("properties", {})
        if "connection_id" in props:
            props["connection_id"]["x-aigw-connection-picker"] = {
                "provider": "claude",
                "aigw_url_field": "aigw_url",
            }
        return schema

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.claude_backend_api.backend import AnthropicBackend
        from screamingface.plugins.claude_backend_api.interpreter import (
            ClaudeBackendApiInterpreter,
        )

        settings: ClaudeBackendApiSettings = self.settings  # type: ignore[assignment]
        aigw_source = _maybe_aigw_source(settings, app)
        backend = AnthropicBackend(aigw_source=aigw_source)

        return ClaudeBackendApiInterpreter(
            app=app,
            settings=settings,
            backend=backend,
        )
