"""Fail-loud contract for gemini-frontend static-spec resolution.

If ``plugin.resolve_context()`` raises while resolving a static (non-$prompt)
url4 spec, the proxy must NOT 500 or silently drop the error — it must return a
``JSONResponse(200)`` whose candidate text contains ``[url4 error]`` and
surfaces the underlying exception message.

This is the regression net for the ``try/except`` around ``resolve_context`` in
``gemini_frontend/proxy.py``: removing it makes this test fail.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings
from screamingface.plugins.gemini_frontend.proxy import create_router

_BOOM = "ensemble exploded"


class _ExplodingPlugin:
    """Plugin whose static resolve always raises."""

    def __init__(self, expression: str) -> None:
        self._expression = expression

    def get_active_expression(self) -> str | None:
        return self._expression

    def resolve_context(self) -> str | None:
        raise RuntimeError(_BOOM)


def _app(settings: GeminiFrontendSettings, plugin: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(create_router(settings, plugin=plugin))
    return app


def _error_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for cand in payload.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            txt = part.get("text")
            if isinstance(txt, str):
                parts.append(txt)
    return "\n".join(parts)


def test_static_resolve_failure_screams() -> None:
    settings = GeminiFrontendSettings(
        upstream_url="https://generativelanguage.googleapis.com",
        active_spec="boom-spec",
        embed_target="user",
        embed_mode="replace",
    )
    # Non-$prompt expression → static-resolve branch (calls resolve_context()).
    plugin = _ExplodingPlugin(expression="(https://docs.example.com)!'answer'")
    client = TestClient(_app(settings, plugin))

    # POST to generateContent (non-streaming: path lacks "streamGenerateContent").
    r = client.post(
        "/v1beta/models/gemini-pro:generateContent",
        json={"contents": [{"role": "user", "parts": [{"text": "Hi"}]}]},
    )

    assert r.status_code == 200
    text = _error_text(r.json())
    assert "[url4 error]" in text
    assert _BOOM in text
