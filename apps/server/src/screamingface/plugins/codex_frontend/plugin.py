"""Codex Frontend plugin — transparent proxy on a dedicated port.

Mirrors claude-frontend: runs its own HTTP server so its routes
(/v1/responses, /v1/*) don't clash with the main SF server.

The Codex CLI uses the OpenAI Responses API, not Chat Completions.

Most behavior lives in :class:`frontend_base.FrontendPluginBase`. This
module declares the Codex-specific overrides only.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from screamingface.plugins.codex_frontend.proxy import create_router
from screamingface.plugins.frontend_base import (
    FrontendPluginBase,
    FrontendSettingsBase,
)


class CodexFrontendSettings(FrontendSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_CODEX_FRONTEND__",
        env_nested_delimiter="__",
    )

    upstream_url: str = "https://api.openai.com"
    listen_port: int = 9102
    default_backend_path: str = "/codex"


class CodexFrontendPlugin(FrontendPluginBase):
    name = "codex-frontend"
    description = "Transparent proxy between Codex CLI and the OpenAI API"
    tags: list[str] = ["product:openai"]
    depends: list[str] = ["url4-executor", "frontend-base"]
    settings_class = CodexFrontendSettings

    cli_binary = "codex"
    cli_install_hint = "Install it with: npm install -g @openai/codex"
    app_title = "codex-frontend"
    create_router = staticmethod(create_router)
