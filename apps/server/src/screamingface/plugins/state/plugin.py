"""StatePlugin — Tortoise ORM lifecycle and model-registration entrypoint.

Other plugins:
  1. Declare `depends = ["state"]` so this plugin's setup() runs first.
  2. In their own setup(), retrieve the StatePlugin instance from
     `app.state.state_plugin` and call .register_models(app_label, modules).
  3. Make sure they do NOT query the DB during setup() — only on/after the
     `app.startup` hook fires.

state itself emits app.startup/app.shutdown callbacks that drive
Tortoise.init / generate_schemas(safe=True) / close_connections.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict
from tortoise import Tortoise

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.state.registry import ModelRegistry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class StateSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_STATE__",
        env_nested_delimiter="__",
        extra="ignore",
    )

    path: Path = Path.home() / ".screamingface" / "state.db"
    echo: bool = False


class StatePlugin(Plugin):
    name = "state"
    description = "Generic stateful storage core — Tortoise ORM + sqlite"
    tags: list[str] = ["product:system"]
    depends: list[str] = []
    settings_class = StateSettings

    def __init__(self) -> None:
        self.registry = ModelRegistry()

    def register_models(self, app_label: str, modules: list[str]) -> None:
        """Public API: declare a plugin's Tortoise models.

        Call from another plugin's setup(). Raises after the state plugin has
        initialized Tortoise (i.e. after the app.startup hook has fired).
        """
        self.registry.register(app_label, modules)

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        # Expose this instance to other plugins so they can call register_models()
        # from their own setup(). Mirrors the data-store plugin's app.state.blob_store.
        app.state.state_plugin = self
        assert isinstance(self.settings, StateSettings)  # set by registry.activate
        settings = self.settings

        async def _on_startup() -> None:
            settings.path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite://{settings.path}"
            config = self.registry.build_config(db_url=db_url)
            if self.registry.is_empty:
                logger.info("state plugin: no models registered, skipping Tortoise.init")
                return
            await Tortoise.init(config=config)
            await Tortoise.generate_schemas(safe=True)
            self.registry.mark_initialized()
            app.state.state_ready = True
            logger.info("state plugin: Tortoise initialized at %s", settings.path)

        async def _on_shutdown() -> None:
            if getattr(app.state, "state_ready", False):
                await Tortoise.close_connections()
                app.state.state_ready = False
                logger.info("state plugin: Tortoise connections closed")

        hooks.register("app.startup", _on_startup, plugin_name=self.name, priority=10)
        hooks.register("app.shutdown", _on_shutdown, plugin_name=self.name, priority=200)
