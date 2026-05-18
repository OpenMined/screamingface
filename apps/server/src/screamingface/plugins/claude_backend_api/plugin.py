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
from screamingface.plugins.claude_backend_api.routes import create_router

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
    create_router = staticmethod(create_router)

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.claude_backend_api.interpreter import (
            ClaudeBackendApiInterpreter,
        )

        return ClaudeBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
