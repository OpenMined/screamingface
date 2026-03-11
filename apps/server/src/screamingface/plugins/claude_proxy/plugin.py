"""Claude Proxy plugin — transparent proxy between Claude Code and the Anthropic API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_proxy.proxy import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class ClaudeProxySettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_PROXY__",
        env_nested_delimiter="__",
    )
    upstream_url: str = "https://api.anthropic.com"
    api_key_env: str = "ANTHROPIC_API_KEY"


class ClaudeProxyPlugin(Plugin):
    name = "claude-proxy"
    description = "Transparent proxy between Claude Code and the Anthropic API"
    settings_class = ClaudeProxySettings

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason
        import shutil

        if not shutil.which("claude"):
            return False, "Claude Code CLI not found in PATH"
        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(self.settings)  # type: ignore[arg-type]
        routes.add_router(self.name, router, prefix="")
