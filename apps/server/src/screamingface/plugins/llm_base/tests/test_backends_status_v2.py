from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.llm_base import routes as status_routes
from screamingface.plugins.llm_base.routes import STATUS_V2_ACCEPT, create_router


def test_legacy_backends_status_exempt_from_desktop_secret(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(create_router(app=None))

    response = TestClient(app).get("/backends/status")

    assert response.status_code == 200
    assert response.json() == {}


def test_status_v2_requires_desktop_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(create_router(app=None))
    client = TestClient(app)

    missing = client.get("/backends/status", headers={"accept": STATUS_V2_ACCEPT})
    allowed = client.get(
        "/backends/status",
        headers={"accept": STATUS_V2_ACCEPT, "X-SF-Desktop-Secret": "test-secret"},
    )

    assert missing.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["version"] == 2


def test_health_exempt_from_desktop_secret(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")
    app = create_app(AppConfig(plugins=[]))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_external_auth_disabled_gateway_fails_closed(monkeypatch) -> None:
    async def reachable(_gateway_url: str) -> bool:
        return True

    async def auth_disabled(_gateway_url: str, *, token: str | None) -> int:  # noqa: ARG001
        return 200

    monkeypatch.setattr(status_routes, "_probe_gateway_healthz", reachable)
    monkeypatch.setattr(status_routes, "_probe_gateway_me", auth_disabled)
    app = SimpleNamespace(
        state=SimpleNamespace(
            config=SimpleNamespace(
                plugin_config={
                    "aigw-base": {
                        "mode": "external",
                        "gateway_url": "https://gateway.example.com",
                    }
                }
            ),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )

    payload = await status_routes._build_status_v2(app)

    assert payload["action"] == "gateway_misconfigured"
    assert payload["gateway"]["reachable"] is True
    assert payload["gateway"]["authenticated"] is False
    assert "provider_auth" not in payload
    assert "backends" not in payload
