"""Built-in plugin for hosted AIGateway OAuth loopback callbacks."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from screamingface.plugin import Plugin
from screamingface.plugins.aigw_base.config import resolve_aigw_runtime_config

from .bridge import AigwCallbackBridge, DisabledAigwCallbackBridge
from .settings import AigwCallbackSettings

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class AigwCallbackPlugin(Plugin):
    name = "aigw-callback"
    description = "Bridges local OAuth callbacks to hosted AIGateway in external mode."
    tags: list[str] = ["product:aigw"]
    depends: list[str] = ["aigw-base"]
    conflicts: list[str] = []
    settings_class = AigwCallbackSettings

    def __init__(self) -> None:
        self._bridge: AigwCallbackBridge | None = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,  # noqa: ARG002
        routes: RouteRegistry,  # noqa: ARG002
    ) -> None:
        settings = cast(AigwCallbackSettings, self.settings)
        if not settings.enabled or resolve_aigw_runtime_config(app).mode != "external":
            app.state.aigw_callback_bridge = DisabledAigwCallbackBridge()
            return

        bridge = AigwCallbackBridge(app=app, settings=settings)
        self._bridge = bridge
        app.state.aigw_callback_bridge = bridge
        hooks.register("app.shutdown", bridge.shutdown, plugin_name=self.name)

    def teardown(self) -> None:
        bridge = self._bridge
        self._bridge = None
        if bridge is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(bridge.shutdown())
            return
        loop.create_task(bridge.shutdown())
