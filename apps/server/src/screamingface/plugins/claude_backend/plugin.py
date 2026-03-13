"""Claude Backend plugin — REST wrapper for the local Claude Code CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_backend.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class ClaudeBackendSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_BACKEND__",
        env_nested_delimiter="__",
    )
    default_model: str | None = None
    default_effort: str = "medium"
    timeout_seconds: float = 300.0
    max_budget_usd: float | None = None
    permission_mode: str | None = None
    dangerously_skip_permissions: bool = False


class ClaudeBackendPlugin(Plugin):
    name = "claude-backend"
    description = "REST wrapper for the local Claude Code CLI"
    settings_class = ClaudeBackendSettings
    system_deps = ["claude"]

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(self.settings)  # type: ignore[arg-type]
        routes.add_router(self.name, router, prefix="")
