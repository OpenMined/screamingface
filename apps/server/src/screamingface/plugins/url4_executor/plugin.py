"""URL4 Executor plugin — url4 protocol engine, parsing, resolution, and HTTP endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.url4_executor.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class Url4ExecutorPlugin(Plugin):
    name = "url4-executor"
    description = "url4 protocol engine — parsing, resolution, and HTTP endpoint"
    tags: list[str] = ["product:url4"]
    depends: list[str] = []
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(app)
        routes.add_router(self.name, router, prefix="")
