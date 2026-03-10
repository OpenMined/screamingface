"""Base Plugin class — the contract every ScreamingFace plugin must implement."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class Plugin:
    """Base class for all ScreamingFace plugins.

    Subclass this and override `setup()` to register hooks, classes, and routes.
    """

    name: str = ""
    version: str = "0.0.1"
    depends: list[str] = []
    description: str = ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        """Called when the plugin is activated. Register hooks, classes, and routes here."""

    def teardown(self) -> None:
        """Called when the plugin is deactivated. Clean up resources here."""
