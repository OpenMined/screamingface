from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from fastapi import FastAPI

from screamingface.plugins.aigw_callback.bridge import (
    AigwCallbackBridge,
    DisabledAigwCallbackBridge,
)
from screamingface.plugins.aigw_callback.plugin import AigwCallbackPlugin
from screamingface.plugins.aigw_callback.settings import AigwCallbackSettings


class _Hooks:
    def __init__(self) -> None:
        self.registrations: list[tuple[str, object, str | None]] = []

    def register(self, event: str, callback: object, *, plugin_name: str | None = None) -> None:
        self.registrations.append((event, callback, plugin_name))


def _app(mode: str) -> FastAPI:
    app = FastAPI()
    app.state.config = SimpleNamespace(plugin_config={"aigw-base": {"mode": mode}})
    return app


def test_plugin_sets_disabled_bridge_in_local_managed_mode() -> None:
    plugin = AigwCallbackPlugin()
    plugin.settings = AigwCallbackSettings()
    hooks = _Hooks()
    app = _app("local_managed")

    plugin.setup(
        app,
        cast(Any, hooks),
        classes=cast(Any, SimpleNamespace()),
        routes=cast(Any, SimpleNamespace()),
    )

    assert isinstance(app.state.aigw_callback_bridge, DisabledAigwCallbackBridge)
    assert hooks.registrations == []


def test_plugin_registers_bridge_and_shutdown_hook_in_external_mode() -> None:
    plugin = AigwCallbackPlugin()
    plugin.settings = AigwCallbackSettings()
    hooks = _Hooks()
    app = _app("external")

    plugin.setup(
        app,
        cast(Any, hooks),
        classes=cast(Any, SimpleNamespace()),
        routes=cast(Any, SimpleNamespace()),
    )

    assert isinstance(app.state.aigw_callback_bridge, AigwCallbackBridge)
    assert len(hooks.registrations) == 1
    event, callback, plugin_name = hooks.registrations[0]
    assert event == "app.shutdown"
    assert callback == app.state.aigw_callback_bridge.shutdown
    assert plugin_name == "aigw-callback"
