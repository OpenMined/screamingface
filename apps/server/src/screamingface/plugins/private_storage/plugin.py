"""PrivateStoragePlugin — DB-backed editable markdown entities at /private/{uuid7}.

Temporary demo-period entity. Same url4 role as /data, but persistent (Tortoise
via the state plugin) and editable from the Private Data UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.private_storage.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class PrivateStoragePlugin(Plugin):
    name = "private-storage"
    description = "Editable markdown entities by uuid7 at /private — url4 content source (demo)"
    tags: list[str] = ["product:system", "lifecycle:demo"]
    depends: list[str] = ["state"]
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        app.state.state_plugin.register_models(
            "private_storage",
            ["screamingface.plugins.private_storage.models"],
        )
        router = create_router()
        routes.add_router(self.name, router, prefix="")
