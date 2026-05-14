from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_base import backend as backend_module
from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)


def test_codex_health_queries_codex_gateway_provider(monkeypatch) -> None:
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url):
            captured["url"] = url
            return httpx.Response(200, json={"state": "authenticated"})

    monkeypatch.setattr(backend_module.httpx, "AsyncClient", FakeAsyncClient)
    app = FastAPI()
    app.include_router(AigwCodexBackendPlugin.create_router(AigwCodexBackendSettings(), app=app))

    resp = TestClient(app).get("/codex/health")

    assert resp.status_code == 200
    assert captured["url"] == "http://127.0.0.1:9105/v1/auth/codex/profiles/default/status"
