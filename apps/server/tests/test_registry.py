"""Tests for the plugin registry."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_has_registries(client: TestClient) -> None:
    app = client.app
    assert hasattr(app.state, "hooks")
    assert hasattr(app.state, "classes")
    assert hasattr(app.state, "routes")
    assert hasattr(app.state, "plugins")
    assert hasattr(app.state, "config")
