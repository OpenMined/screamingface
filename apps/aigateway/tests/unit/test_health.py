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


def test_providers_lists_loaded_credential_capabilities(authenticated_client) -> None:
    resp = authenticated_client.get("/v1/providers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    providers = {row["id"]: row for row in body["data"]}
    assert providers["anthropic"] == {
        "object": "provider",
        "id": "anthropic",
        "display_name": "Anthropic",
        "auth_methods": ["api_key", "oauth"],
    }
    assert providers["codex"]["auth_methods"] == ["oauth"]
    assert providers["gemini-cli"]["display_name"] == "Gemini CLI"
    assert "ollama" not in providers
    assert "openrouter" not in providers


def test_providers_requires_auth(client) -> None:
    resp = client.get("/v1/providers")
    assert resp.status_code == 401
