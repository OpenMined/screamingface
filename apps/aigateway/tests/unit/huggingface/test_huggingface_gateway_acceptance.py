"""End-to-end gateway acceptance for Hugging Face (SF-345).

Proves the shared, provider-generic surfaces work for the new provider with NO
per-provider route/table code:
- ``GET /v1/models`` lists HF ids with ``owned_by == "huggingface"``;
- ``POST /v1/oauth/connections/api-key`` creates an HF api-key connection and
  writes the key to the same encrypted credential-blob slot the chat path reads,
  never echoing it back.
"""

from __future__ import annotations

import json

from aigateway.core.oauth.store import credential_key_for
from aigateway.plugins.huggingface_provider.plugin import _credential_service_for

_HF_KEY = "hf_test_connection_key_1234567890"


def test_models_lists_huggingface_owner(authenticated_client) -> None:
    resp = authenticated_client.get("/v1/models")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    owners = {entry["owned_by"] for entry in data}
    assert "huggingface" in owners
    hf_ids = [e["id"] for e in data if e["owned_by"] == "huggingface"]
    assert hf_ids, "no huggingface models surfaced"
    assert all(mid.startswith("huggingface/") for mid in hf_ids)
    assert "huggingface/deepseek-ai/DeepSeek-R1:novita" in hf_ids


def test_create_api_key_connection_for_huggingface(authenticated_client) -> None:
    resp = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "huggingface", "api_key": _HF_KEY, "label": "my-hf-key"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "active"
    assert data["auth_type"] == "api_key"
    assert data["provider"] == "huggingface"
    assert data["label"] == "my-hf-key"
    # The raw token must never be echoed back.
    assert _HF_KEY not in resp.text


def test_api_key_connection_without_label_succeeds(authenticated_client) -> None:
    # HF does not require an up-front label (requires_oauth_connection_label() is False).
    resp = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "huggingface", "api_key": _HF_KEY},
    )
    assert resp.status_code == 201, resp.text


def test_key_written_to_chat_read_slot_encrypted(authenticated_client, credential_blobs) -> None:
    resp = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "huggingface", "api_key": _HF_KEY, "label": "my-hf-key"},
    )
    data = resp.json()
    # Same slot the chat path rebuilds: service = aigateway:huggingface:<account>:<conn>.
    service = _credential_service_for(credential_key_for(data["account_id"], data["id"]))
    decrypted = credential_blobs.read(service, "default")
    assert json.loads(decrypted) == {"auth_type": "api_key", "api_key": _HF_KEY}
    # At-rest ciphertext must not contain the plaintext token.
    assert _HF_KEY not in (credential_blobs.read_raw(service, "default") or "")
