"""aigw-base plugin: registers the shared base classes for aigw_* plugins.

This plugin has no routes of its own. It exists so the package can be
discovered by the SF plugin loader (entry-point group `screamingface.plugins`)
and so other plugins can declare `depends=["aigw-base"]`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class AigwBasePlugin(Plugin):
    name = "aigw-base"
    description = "Shared base classes for aigw_*_backend plugins."
    tags: list[str] = ["product:aigw"]
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = []

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,  # noqa: ARG002
        classes: ClassRegistry,  # noqa: ARG002
        routes: RouteRegistry,  # noqa: ARG002
    ) -> None:
        # No-op: this package is base classes only.
        return None
