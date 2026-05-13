"""ModelRegistry — collects per-plugin model module paths and builds the Tortoise config.

Other plugins call StatePlugin.register_models() during their own setup() phase.
The collected entries are turned into a Tortoise config dict on startup, when the
state plugin's app.startup hook fires.
"""

from __future__ import annotations

from typing import Any


class ModelRegistry:
    def __init__(self) -> None:
        self._apps: dict[str, list[str]] = {}
        self._initialized: bool = False

    @property
    def is_empty(self) -> bool:
        return not self._apps

    def register(self, app_label: str, modules: list[str]) -> None:
        if self._initialized:
            raise RuntimeError(
                "state plugin already initialized; register models in setup() before app.startup"
            )
        if not modules:
            raise ValueError("at least one module must be provided")
        if app_label in self._apps:
            raise ValueError(f"app_label {app_label!r} is already registered")
        self._apps[app_label] = list(modules)

    def mark_initialized(self) -> None:
        self._initialized = True

    def build_config(self, *, db_url: str) -> dict[str, Any]:
        return {
            "connections": {"default": db_url},
            "apps": {
                label: {"models": list(mods), "default_connection": "default"}
                for label, mods in self._apps.items()
            },
            "use_tz": True,
            "timezone": "UTC",
        }
