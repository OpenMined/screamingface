from __future__ import annotations

from fastapi.testclient import TestClient

from aigateway.main import create_app


def test_healthz() -> None:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_models_lists_loaded_providers() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    owners = {entry["owned_by"] for entry in body["data"]}
    assert "anthropic" in owners
