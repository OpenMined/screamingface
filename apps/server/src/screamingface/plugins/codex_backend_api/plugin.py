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
from screamingface.plugins.codex_backend_api.routes import create_router

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
    create_router = staticmethod(create_router)

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.codex_backend_api.interpreter import (
            CodexBackendApiInterpreter,
        )

        return CodexBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
