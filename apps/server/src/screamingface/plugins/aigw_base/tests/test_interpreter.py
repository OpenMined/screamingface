"""Unit tests for AigwInterpreter — verifies process() semantics."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from screamingface.plugins.aigw_base.backend import AigwBackend
from screamingface.plugins.aigw_base.interpreter import AigwInterpreter
from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def _factory_returning(text: str):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    def factory(timeout: float):
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout))

    return factory


@pytest.mark.anyio
async def test_process_combines_intent_and_sources() -> None:
    backend = AigwBackend(
        gateway_provider="test-provider",
        http_client_factory=_factory_returning("answer"),
    )
    interp = AigwInterpreter(backend=backend)
    out = await interp.process(sources="cats are mammals", intent="what are cats?")
    assert out == "answer"


@pytest.mark.anyio
async def test_process_returns_empty_when_no_input() -> None:
    backend = AigwBackend(
        gateway_provider="test-provider",
        http_client_factory=_factory_returning("X"),
    )
    interp = AigwInterpreter(backend=backend)
    assert await interp.process(sources="", intent=None) == ""


def test_plugin_setup_and_interpreter_share_backend(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def create_router(settings, app=None, *, backend=None):  # noqa: ANN001
        captured["backend"] = backend
        return APIRouter()

    class _Routes:
        def add_router(self, name, router, prefix=""):  # noqa: ANN001, ARG002
            return None

    monkeypatch.setattr(AigwClaudeBackendPlugin, "create_router", staticmethod(create_router))
    plugin = AigwClaudeBackendPlugin()
    plugin.settings = AigwClaudeBackendSettings()
    app = FastAPI()

    plugin.setup(
        app=app,
        hooks=cast(Any, None),
        classes=cast(Any, None),
        routes=cast(Any, _Routes()),
    )
    interpreter = plugin._make_interpreter(app)

    assert captured["backend"] is interpreter._backend
