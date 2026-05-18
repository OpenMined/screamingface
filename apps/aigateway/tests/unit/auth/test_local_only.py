from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aigateway.config import Settings
from aigateway.core.auth.local_only import AuthDisabledLocalOnlyMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthDisabledLocalOnlyMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_auth_disabled_local_only_allows_loopback_client_and_host() -> None:
    with TestClient(
        _app(),
        base_url="http://127.0.0.1:9105",
        client=("127.0.0.1", 50000),
    ) as client:
        response = client.get("/ok")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_disabled_local_only_allows_localhost_host() -> None:
    with TestClient(
        _app(),
        base_url="http://localhost:9105",
        client=("127.0.0.1", 50000),
    ) as client:
        response = client.get("/ok")

    assert response.status_code == 200


def test_auth_disabled_local_only_rejects_dns_rebinding_host() -> None:
    with TestClient(
        _app(),
        base_url="http://example.test:9105",
        client=("127.0.0.1", 50000),
    ) as client:
        response = client.get("/ok")

    assert response.status_code == 403
    assert "loopback" in response.text


def test_auth_disabled_local_only_rejects_non_loopback_client() -> None:
    with TestClient(
        _app(),
        base_url="http://127.0.0.1:9105",
        client=("192.168.1.50", 50000),
    ) as client:
        response = client.get("/ok")

    assert response.status_code == 403
    assert "loopback" in response.text


def test_create_app_installs_local_only_middleware_when_auth_disabled() -> None:
    from aigateway.main import create_app

    app = create_app(Settings(auth_enabled=False))

    assert any(
        middleware.cls is AuthDisabledLocalOnlyMiddleware for middleware in app.user_middleware
    )


def test_create_app_does_not_install_local_only_middleware_when_auth_enabled() -> None:
    from aigateway.main import create_app

    app = create_app(Settings(auth_enabled=True))

    assert not any(
        middleware.cls is AuthDisabledLocalOnlyMiddleware for middleware in app.user_middleware
    )
