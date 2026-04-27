"""Data Store plugin — in-memory key-value blob store for URL4."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.data_store.routes import create_router
from screamingface.plugins.data_store.storage import BlobStore

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class DataStorePlugin(Plugin):
    name = "data-store"
    description = "In-memory key-value data store — turn user data into fetchable URLs for URL4"
    tags: list[str] = ["product:system"]
    depends: list[str] = []
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        app.state.blob_store = BlobStore()
        router = create_router()
        routes.add_router(self.name, router, prefix="")
