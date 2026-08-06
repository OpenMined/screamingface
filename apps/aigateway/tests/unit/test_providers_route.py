"""Credential-provider discovery derived from the loaded plugin registry."""

from __future__ import annotations


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


def test_providers_is_available_when_local_auth_is_explicitly_disabled(client) -> None:
    client.app.state.settings.auth_mode = "disabled"

    resp = client.get("/v1/providers")

    assert resp.status_code == 200
    assert resp.json()["object"] == "list"
