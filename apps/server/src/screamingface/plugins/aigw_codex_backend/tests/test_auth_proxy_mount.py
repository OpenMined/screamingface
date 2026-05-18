from __future__ import annotations

import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Route

from screamingface.plugins.aigw_base import auth_proxy_router as apr
from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)


def test_aigw_codex_backend_mounts_browser_auth_proxy_routes_without_import() -> None:
    app = FastAPI()
    settings = AigwCodexBackendSettings()
    router = AigwCodexBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    routes = {r.path: r for r in app.routes if isinstance(r, Route)}
    assert "/codex/auth/start" in routes
    assert "/codex/auth/status" in routes
    assert "/codex/auth/profiles" in routes
    assert "/codex/auth/profiles/{name}" in routes
    assert "/codex/auth/exchange-code" in routes
    assert "/codex/auth/import" not in routes


def test_aigw_codex_backend_passes_defaults_to_gateway_oauth_start() -> None:
    settings = AigwCodexBackendSettings(
        default_model="codex/gpt-5.4-mini",
        default_effort="medium",
        timeout_seconds=300.0,
    )
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/profiles"):
            captured["url"] = str(req.url)
            captured["body"] = json.loads(req.read().decode())
            return httpx.Response(201, json={"profile_id": "codex:default"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    original = apr._default_http_factory
    apr._default_http_factory = http_factory  # type: ignore[assignment]
    try:
        app = FastAPI()
        router = AigwCodexBackendPlugin.create_router(settings, app=app)
        app.include_router(router)
        response = TestClient(app).post("/codex/auth/start")
        assert response.status_code == 201
    finally:
        apr._default_http_factory = original  # type: ignore[assignment]

    assert captured["url"] == "http://127.0.0.1:9105/v1/auth/codex/profiles"
    assert captured["body"] == {
        "name": "default",
        "defaults": {
            "model": "codex/gpt-5.4-mini",
            "timeout_seconds": 300.0,
            "reasoning_effort": "medium",
        },
    }
