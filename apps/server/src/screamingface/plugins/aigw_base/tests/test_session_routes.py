from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_base.client import gateway_session_state
from screamingface.plugins.aigw_base.routes import create_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.state.config = SimpleNamespace(
        plugin_config={"aigw-base": {"mode": "external", "gateway_url": "http://127.0.0.1:9105"}}
    )
    app.state.plugins = SimpleNamespace(active_plugins={})
    app.include_router(create_router(app))
    return app


def test_gateway_login_returns_token_but_session_status_does_not(monkeypatch) -> None:
    app = _make_app()
    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    captured: dict[str, Any] = {}

    class FakeGatewayClient:
        def __init__(self, gateway_app: Any) -> None:
            assert gateway_app is app

        async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
            captured["method"] = method
            captured["path"] = path
            captured["kwargs"] = kwargs
            return httpx.Response(
                200,
                json={"token": "jwt-token", "expires_at": expires_at},
                request=httpx.Request(method, "http://gateway/v1/auth/login"),
            )

    monkeypatch.setattr(
        "screamingface.plugins.aigw_base.routes.AigwGatewayClient", FakeGatewayClient
    )

    client = TestClient(app)
    login = client.post(
        "/aigateway/session/login",
        json={"username": "admin", "password": "secret"},
    )

    assert login.status_code == 200
    assert login.json() == {
        "authenticated": True,
        "expires_at": expires_at,
        "token": "jwt-token",
    }
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/auth/login"
    assert captured["kwargs"]["json"] == {"username": "admin", "password": "secret"}
    assert captured["kwargs"]["allow_unauthenticated"] is True
    assert gateway_session_state(app).valid_token() == "jwt-token"

    status = client.get("/aigateway/session")

    assert status.status_code == 200
    assert status.json() == {
        "mode": "external",
        "authenticated": True,
        "expires_at": expires_at,
    }


def test_gateway_login_applies_gateway_url_override(monkeypatch) -> None:
    app = _make_app()
    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    captured: dict[str, Any] = {}

    class FakeGatewayClient:
        def __init__(self, gateway_app: Any) -> None:
            assert gateway_app is app

        async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
            captured["runtime_url"] = app.state.config.plugin_config["aigw-base"]["gateway_url"]
            return httpx.Response(
                200,
                json={"token": "jwt-token", "expires_at": expires_at},
                request=httpx.Request(method, "https://gateway.example.com/v1/auth/login"),
            )

    monkeypatch.setattr(
        "screamingface.plugins.aigw_base.routes.AigwGatewayClient", FakeGatewayClient
    )

    response = TestClient(app).post(
        "/aigateway/session/login",
        json={
            "username": "admin",
            "password": "secret",
            "gateway_url": "https://gateway.example.com/",
        },
    )

    assert response.status_code == 200
    assert captured["runtime_url"] == "https://gateway.example.com"
    assert (
        app.state.config.plugin_config["aigw-base"]["gateway_url"] == "https://gateway.example.com"
    )


def test_gateway_login_rejects_insecure_non_loopback_gateway_url() -> None:
    app = _make_app()

    response = TestClient(app).post(
        "/aigateway/session/login",
        json={
            "username": "admin",
            "password": "secret",
            "gateway_url": "http://gateway.example.com",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_gateway_url"


def test_gateway_login_rejects_preconfigured_insecure_non_loopback_url(monkeypatch) -> None:
    app = _make_app()
    app.state.config.plugin_config["aigw-base"]["gateway_url"] = "http://gateway.example.com"

    class FakeGatewayClient:
        def __init__(self, gateway_app: Any) -> None:
            assert gateway_app is app

        async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
            raise AssertionError("gateway login should fail before credentials are sent")

    monkeypatch.setattr(
        "screamingface.plugins.aigw_base.routes.AigwGatewayClient", FakeGatewayClient
    )

    response = TestClient(app).post(
        "/aigateway/session/login",
        json={"username": "admin", "password": "secret"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_gateway_url"
