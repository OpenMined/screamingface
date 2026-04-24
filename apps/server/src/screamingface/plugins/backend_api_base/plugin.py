"""backend-api-base SF plugin.

Registers no routes, no hooks, no settings. Exists only so other
plugins can declare ``depends = ["backend-api-base"]`` and the
dependency machinery handles activation ordering.

The public API is the Python import surface exposed by
``screamingface.plugins.backend_api_base.__init__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class BackendApiBasePlugin(Plugin):
    name = "backend-api-base"
    description = (
        "Shared wire-format models (RunRequest/RunResponse/BackendProfile/"
        "FileInput) for every *_backend_api plugin. No routes, hooks, or "
        "settings — other plugins import from it to stay aligned on the "
        "HTTP contract used across the ensemble."
    )
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
        pass
