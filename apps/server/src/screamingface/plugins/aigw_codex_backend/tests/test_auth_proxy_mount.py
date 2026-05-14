from __future__ import annotations

import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Route

from screamingface.plugins.aigw_codex_backend._defaults import (
    _build_profile_defaults_from_settings,
)
from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)
from screamingface.plugins.backend_api_base.models import BackendProfile


def test_aigw_codex_backend_mounts_import_auth_proxy_routes_only() -> None:
    app = FastAPI()
    router = AigwCodexBackendPlugin.create_router(AigwCodexBackendSettings(), app=app)
    app.include_router(router)

    paths = {r.path for r in app.routes if isinstance(r, Route)}
    assert "/codex/auth/import" in paths
    assert "/codex/auth/status" in paths
    assert "/codex/auth/profiles" in paths
    assert "/codex/auth/profiles/{name}" in paths
    assert "/codex/auth/start" not in paths
    assert "/codex/auth/exchange-code" not in paths


def test_build_profile_defaults_top_level_settings() -> None:
    settings = AigwCodexBackendSettings(
        default_model="codex/gpt-5.4-mini",
        default_effort="high",
        timeout_seconds=300.0,
    )

    assert _build_profile_defaults_from_settings(settings) == {
        "model": "codex/gpt-5.4-mini",
        "timeout_seconds": 300.0,
        "reasoning_effort": "high",
    }


def test_build_profile_defaults_profile_overrides_top_level() -> None:
    settings = AigwCodexBackendSettings(
        default_model="codex/gpt-5.4-mini",
        default_effort="medium",
        timeout_seconds=300.0,
        default_profile="default",
        profiles={
            "default": BackendProfile(
                model="codex/gpt-5.5",
                system_prompt="Profile prompt.",
                effort="high",
                timeout_seconds=120.0,
            )
        },
    )

    assert _build_profile_defaults_from_settings(settings) == {
        "model": "codex/gpt-5.5",
        "system_prompt": "Profile prompt.",
        "timeout_seconds": 120.0,
        "reasoning_effort": "high",
    }


def test_build_profile_defaults_drops_max_effort() -> None:
    settings = AigwCodexBackendSettings(
        default_model="codex/gpt-5.4-mini",
        default_effort="max",
        timeout_seconds=300.0,
    )

    out = _build_profile_defaults_from_settings(settings)

    assert "reasoning_effort" not in out
    assert out["model"] == "codex/gpt-5.4-mini"
    assert out["timeout_seconds"] == 300.0


def test_build_profile_defaults_all_none_returns_empty() -> None:
    settings = AigwCodexBackendSettings(default_model=None, default_effort="max")
    object.__setattr__(settings, "timeout_seconds", None)

    assert _build_profile_defaults_from_settings(settings) == {}


def test_import_route_forwards_codex_defaults(monkeypatch) -> None:
    from screamingface.plugins.aigw_base import auth_proxy_router as apr

    settings = AigwCodexBackendSettings(
        default_model="codex/gpt-5.4-mini",
        default_effort="medium",
        timeout_seconds=300.0,
    )
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(201, json={"id": "codex:default", "state": "authenticated"})

    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    monkeypatch.setattr(apr, "_default_http_factory", http_factory)

    app = FastAPI()
    app.include_router(AigwCodexBackendPlugin.create_router(settings, app=app))
    resp = TestClient(app).post("/codex/auth/import")

    assert resp.status_code == 201
    assert captured["url"] == "http://127.0.0.1:9105/v1/auth/codex/profiles/import"
    assert captured["body"] == {
        "name": "default",
        "defaults": {
            "model": "codex/gpt-5.4-mini",
            "timeout_seconds": 300.0,
            "reasoning_effort": "medium",
        },
    }
