"""URL Executor plugin — url4 context resolution endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.url_executor.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class UrlExecutorSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_URL_EXECUTOR__",
        env_nested_delimiter="__",
    )


class UrlExecutorPlugin(Plugin):
    name = "url-executor"
    description = "url4 context resolution endpoint"
    settings_class = UrlExecutorSettings
    depends: list[str] = []

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(self.settings)  # type: ignore[arg-type]
        routes.add_router(self.name, router, prefix="")
