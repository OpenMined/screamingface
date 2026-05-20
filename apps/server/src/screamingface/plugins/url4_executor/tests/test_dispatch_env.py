"""Test that _dispatch_backend_call forwards `env` to handle_backend_call (SF-165)."""

from __future__ import annotations

import pytest

from screamingface.plugin import Plugin
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import Url4BackendCall, Url4Text
from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call


class _SpyPlugin(Plugin):
    name = "spy"
    backend_call_paths = ["/spy"]

    def __init__(self) -> None:
        self.received_env: Env | None = None

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        self.received_env = env
        return "ok"


class _Registry:
    def __init__(self, plugin):
        self.active_plugins = {"spy": plugin}


@pytest.mark.asyncio
async def test_dispatch_forwards_env_to_plugin():
    from fastapi import FastAPI

    app = FastAPI()
    plugin = _SpyPlugin()
    app.state.plugins = _Registry(plugin)

    env = Env.root().child(__run_id__="abc", __run_spec__="hle-x")
    node = Url4BackendCall(path="/spy", intent=Url4Text(value="payload"))

    await _dispatch_backend_call(node, app, env)

    assert plugin.received_env is not None
    assert plugin.received_env.lookup("__run_id__") == "abc"
    assert plugin.received_env.lookup("__run_spec__") == "hle-x"
