"""frontend-base SF plugin — registration stub.

No routes, no settings, no hooks. Exists so other plugins can declare
``depends = ["frontend-base"]``. The public API is the Python import
surface at :mod:`screamingface.plugins.frontend_base`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class FrontendBasePlugin(Plugin):
    name = "frontend-base"
    description = (
        "Shared tracing + redaction helpers (ProxyTracer, truncate, "
        "redact_headers) for every *_frontend proxy plugin. No routes, "
        "hooks, or settings — other plugins import from it so every "
        "frontend emits OTEL spans the same way."
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
