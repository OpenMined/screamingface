"""Claude Frontend plugin — transparent proxy on a dedicated port.

Runs its own HTTP server so its routes (/v1/messages, /v1/*, /api/*) don't
clash with the main SF server or other frontend plugins.

Most behavior lives in :class:`frontend_base.FrontendPluginBase`. This
module declares the Claude-specific overrides only.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from screamingface.plugins.claude_frontend.proxy import create_router
from screamingface.plugins.frontend_base import (
    FrontendPluginBase,
    FrontendSettingsBase,
)


class ClaudeFrontendSettings(FrontendSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_FRONTEND__",
        env_nested_delimiter="__",
    )

    upstream_url: str = "https://api.anthropic.com"
    listen_port: int = 9101
    default_backend_path: str = "/claude"

    filter_auxiliary_requests: bool = True
    """When True, requests whose ``model`` matches ``utility_models`` AND which do
    NOT carry Claude Code's main-loop signature are answered with a synthetic stub
    instead of being resolved via /ensemble (Claude Code's Haiku title/topic/quota
    calls). Set False for pure today-behavior."""

    utility_models: list[str] = ["haiku"]
    """Case-insensitive substrings identifying the utility/auxiliary model tier.
    A request's ``model`` matches if it contains any of these (so 'haiku' covers
    claude-3-5-haiku and claude-haiku-4-5, dated or undated). Set to ``[]`` to
    disable model-based classification (e.g. when Haiku is the user's MAIN model)."""


class ClaudeFrontendPlugin(FrontendPluginBase):
    name = "claude-frontend"
    description = "Transparent proxy between Claude Code and the Anthropic API"
    tags: list[str] = ["product:claude"]
    depends: list[str] = ["url4-executor", "frontend-base"]
    settings_class = ClaudeFrontendSettings

    cli_binary = "claude"
    cli_install_hint = "Install it from https://docs.anthropic.com/en/docs/claude-code"
    app_title = "claude-frontend"
    create_router = staticmethod(create_router)
