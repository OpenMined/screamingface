"""API-key connection endpoints (SF-291 / D-AIGW-018).

POST /v1/oauth/connections/api-key       — create an api-key connection
PUT  /v1/oauth/connections/{id}/api-key  — replace the key

The key is written to the SAME credential-blob slot the chat path reads for a
connection (credential_key_for(account_id, connection.id)), encrypted at rest,
and never echoed back.
"""

from __future__ import annotations

import json

from aigateway.core.oauth.store import credential_key_for
from aigateway.plugins.anthropic_provider.auth import (
    credential_service_for as anthropic_service_for,
)

_KEY = "sk-ant-api03-test-connection-key"


def _create(client, *, provider="anthropic", label: str | None = "work", api_key=_KEY):
    body: dict[str, str] = {"provider": provider, "api_key": api_key}
    if label is not None:
        body["label"] = label
    return client.post("/v1/oauth/connections/api-key", json=body)


def test_create_api_key_connection_is_active_and_typed(authenticated_client) -> None:
    resp = _create(authenticated_client)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "active"
    assert data["auth_type"] == "api_key"
    assert data["label"] == "work"
    assert data["provider"] == "anthropic"
    # The raw key must never be echoed back.
    assert _KEY not in resp.text


def test_create_writes_key_to_chat_read_slot_encrypted(
    authenticated_client, credential_blobs
) -> None:
    resp = _create(authenticated_client)
    data = resp.json()
    service = anthropic_service_for(credential_key_for(data["account_id"], data["id"]))
    # Decrypted blob is the api-key blob the chat path expects.
    decrypted = credential_blobs.read(service, "default")
    assert json.loads(decrypted) == {"auth_type": "api_key", "api_key": _KEY}
    # At-rest ciphertext does not contain the plaintext key.
    assert _KEY not in (credential_blobs.read_raw(service, "default") or "")


def test_create_anthropic_requires_label(authenticated_client) -> None:
    resp = _create(authenticated_client, label=None)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "label_required"


def test_create_duplicate_label_conflicts(authenticated_client) -> None:
    assert _create(authenticated_client, label="dup").status_code == 201
    resp = _create(authenticated_client, label="dup")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "label_conflict"


def test_create_codex_is_api_key_not_supported(authenticated_client) -> None:
    resp = _create(authenticated_client, provider="codex", label="cdx")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "api_key_not_supported"


def test_create_short_key_rejected(authenticated_client) -> None:
    resp = _create(authenticated_client, api_key="short")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_api_key"


def test_create_requires_auth(client) -> None:
    resp = _create(client)
    assert resp.status_code == 401


def test_list_connections_exposes_auth_type(authenticated_client) -> None:
    _create(authenticated_client, label="listed")
    listing = authenticated_client.get("/v1/oauth/connections")
    assert listing.status_code == 200
    rows = listing.json()["connections"]
    assert any(c["label"] == "listed" and c["auth_type"] == "api_key" for c in rows)


def test_replace_key_updates_blob(authenticated_client, credential_blobs) -> None:
    created = _create(authenticated_client, label="rotate").json()
    new_key = "sk-ant-api03-rotated-key-value"
    resp = authenticated_client.put(
        f"/v1/oauth/connections/{created['id']}/api-key",
        json={"api_key": new_key},
    )
    assert resp.status_code == 200, resp.text
    assert new_key not in resp.text
    service = anthropic_service_for(credential_key_for(created["account_id"], created["id"]))
    assert json.loads(credential_blobs.read(service, "default"))["api_key"] == new_key


def test_replace_key_on_missing_connection_404(authenticated_client) -> None:
    resp = authenticated_client.put(
        "/v1/oauth/connections/00000000-0000-0000-0000-000000000000/api-key",
        json={"api_key": _KEY},
    )
    assert resp.status_code == 404


def test_api_key_connection_token_endpoint_rejected(authenticated_client) -> None:
    """An api-key connection has no OAuth token; /token must 400, not mint one."""
    created = _create(authenticated_client, label="notoken").json()
    resp = authenticated_client.get(f"/v1/oauth/connections/{created['id']}/token")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "connection_not_oauth"
