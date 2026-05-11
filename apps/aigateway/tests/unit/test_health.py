from __future__ import annotations


def test_healthz(client) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_models_lists_loaded_providers(authenticated_client) -> None:
    resp = authenticated_client.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    owners = {entry["owned_by"] for entry in body["data"]}
    assert "anthropic" in owners


def test_models_requires_auth(client) -> None:
    resp = client.get("/v1/models")
    assert resp.status_code == 401
