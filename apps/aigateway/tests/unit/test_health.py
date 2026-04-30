from __future__ import annotations

from fastapi.testclient import TestClient

from aigateway.main import create_app


def test_healthz() -> None:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_models_empty_when_no_plugins() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json() == {"object": "list", "data": []}
