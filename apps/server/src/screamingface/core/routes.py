"""Dynamic route registry — add and remove FastAPI routers by plugin name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI


@dataclass
class RouteRecord:
    """Tracks a router added by a plugin."""

    plugin_name: str
    router: APIRouter
    prefix: str


class RouteRegistry:
    """Manage FastAPI routers per plugin, supporting dynamic add/remove."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._records: list[RouteRecord] = []

    def add_router(self, plugin_name: str, router: APIRouter, *, prefix: str = "") -> None:
        """Include a router in the app, tagged with the plugin name."""
        self._records.append(RouteRecord(plugin_name=plugin_name, router=router, prefix=prefix))
        self._app.include_router(router, prefix=prefix, tags=[plugin_name])

    def remove_plugin_routes(self, plugin_name: str) -> None:
        """Remove all routes added by a plugin by rebuilding the app's route list."""
        self._records = [r for r in self._records if r.plugin_name != plugin_name]
        self._rebuild_routes()

    def _rebuild_routes(self) -> None:
        """Rebuild app routes from scratch using current records."""
        # Remove all non-default routes
        from starlette.routing import Route

        # Keep only the built-in routes (openapi, docs, etc.)
        default_paths = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
        self._app.router.routes = [
            r
            for r in self._app.router.routes
            if isinstance(r, Route) and r.path in default_paths or not isinstance(r, Route)
        ]

        # Re-include all tracked routers
        for record in self._records:
            self._app.include_router(record.router, prefix=record.prefix, tags=[record.plugin_name])

    def list_plugin_routes(self, plugin_name: str) -> list[str]:
        """Return prefixes for all routers registered by a plugin."""
        return [r.prefix for r in self._records if r.plugin_name == plugin_name]

    def list_all_plugins(self) -> list[str]:
        """Return plugin names that have registered routes."""
        return sorted({r.plugin_name for r in self._records})
