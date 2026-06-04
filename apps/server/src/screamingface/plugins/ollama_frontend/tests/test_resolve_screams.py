"""Fail-loud contract for ollama-frontend static-spec resolution.

If ``plugin.resolve_context()`` raises while resolving a static (non-$prompt)
url4 spec, the proxy must NOT 500 or silently drop the error — it must return a
``JSONResponse(200)`` whose assistant message text contains ``[url4 error]`` and
surfaces the underlying exception message.

This is the regression net for the ``try/except`` around ``resolve_context`` in
``ollama_frontend/proxy.py``: removing it makes this test fail.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.ollama_frontend.plugin import OllamaFrontendSettings
from screamingface.plugins.ollama_frontend.proxy import create_router

_BOOM = "ensemble exploded"


class _ExplodingPlugin:
    """Plugin whose static resolve always raises."""

    def __init__(self, expression: str) -> None:
        self._expression = expression

    def get_active_expression(self) -> str | None:
        return self._expression

    def resolve_context(self) -> str | None:
        raise RuntimeError(_BOOM)


def _app(settings: OllamaFrontendSettings, plugin: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(create_router(settings, plugin=plugin))
    return app


def test_static_resolve_failure_screams() -> None:
    settings = OllamaFrontendSettings(
        upstream_url="http://localhost:11434",
        active_spec="boom-spec",
        embed_target="user",
        embed_mode="replace",
    )
    # Non-$prompt expression → static-resolve branch (calls resolve_context()).
    plugin = _ExplodingPlugin(expression="(https://docs.example.com)!'answer'")
    client = TestClient(_app(settings, plugin))

    r = client.post(
        "/api/chat",
        json={
            "model": "llama3",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        },
    )

    assert r.status_code == 200
    text = r.json()["message"]["content"]
    assert "[url4 error]" in text
    assert _BOOM in text
