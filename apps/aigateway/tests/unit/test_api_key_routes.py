"""Route tests for the profile API-key path (SF-244).

Mirrors the OAuth route tests: authenticated_client + the credential_blobs
probe (which decrypts through the same master key as the app's ORMStore).
"""

from __future__ import annotations

import json

import httpx
import pytest

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from aigateway.plugins.anthropic_provider.auth import credential_service_for
from aigateway.plugins.gemini_provider.auth import (
    credential_service_for as gemini_credential_service_for,
)

ANTHROPIC_KEY = "sk-ant-api03-test-key-1234"


def _oauth_token_factory():
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(
            200,
            json={
                "access_token": "oauth-tok",
                "refresh_token": "oauth-rt",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def _put_api_key(client, provider: str, name: str, api_key: str, **extra):
    return client.put(
        f"/v1/auth/{provider}/profiles/{name}/api-key",
        json={"api_key": api_key, **extra},
    )


def test_set_api_key_creates_authenticated_profile(authenticated_client, credential_blobs) -> None:
    account_id = _account_id(authenticated_client)

    resp = _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "authenticated"
    assert body["auth_type"] == "api_key"
    assert body["account_label"].endswith("1234")
    # The raw key is never echoed back.
    assert ANTHROPIC_KEY not in resp.text

    service = credential_service_for(credential_name_for(account_id, "keyed"))
    blob = credential_blobs.read(service, "default")
    assert blob is not None
    assert json.loads(blob) == {"auth_type": "api_key", "api_key": ANTHROPIC_KEY}

    status = authenticated_client.get("/v1/auth/anthropic/profiles/keyed/status")
    assert status.status_code == 200
    assert status.json()["state"] == "authenticated"
    assert status.json()["auth_type"] == "api_key"


def test_set_api_key_replaces_existing_key(authenticated_client, credential_blobs) -> None:
    account_id = _account_id(authenticated_client)
    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )

    resp = _put_api_key(authenticated_client, "anthropic", "keyed", "sk-ant-api03-rotated-9999")

    assert resp.status_code == 200
    assert resp.json()["account_label"].endswith("9999")
    service = credential_service_for(credential_name_for(account_id, "keyed"))
    assert json.loads(credential_blobs.read(service, "default"))["api_key"] == (
        "sk-ant-api03-rotated-9999"
    )


@pytest.mark.asyncio
async def test_set_api_key_over_oauth_profile_flips_auth_type(
    authenticated_client, credential_blobs
) -> None:
    """A profile is exactly one auth at a time: setting a key on an EXISTING
    authenticated OAuth profile replaces the token blob in the shared
    credential slot and flips auth_type/account_label/scopes (audit F17/F24)."""
    account_id = _account_id(authenticated_client)
    idx = ProfileIndexStore(credential_store=credential_blobs.store)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            auth_type="oauth",
            account_label="user@example.com",
            scopes=["org:create_api_key"],
        )
    )
    service = credential_service_for(credential_name_for(account_id, "default"))
    credential_blobs.write(
        service,
        "default",
        json.dumps(
            {
                "access_token": "tok",
                "refresh_token": "rt",
                "expires_at_ms": 1,
                "token_type": "Bearer",
            }
        ),
    )

    resp = _put_api_key(authenticated_client, "anthropic", "default", ANTHROPIC_KEY)

    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_type"] == "api_key"
    assert body["account_label"] == "API key ····1234"
    assert body["scopes"] == []  # OAuth scopes are meaningless for API keys
    assert json.loads(credential_blobs.read(service, "default")) == {
        "auth_type": "api_key",
        "api_key": ANTHROPIC_KEY,
    }


def test_set_api_key_accepts_defaults(authenticated_client) -> None:
    resp = _put_api_key(
        authenticated_client,
        "anthropic",
        "keyed",
        ANTHROPIC_KEY,
        defaults={"max_tokens": 2048},
    )

    assert resp.status_code == 200
    assert resp.json()["defaults"]["max_tokens"] == 2048


def test_set_api_key_unknown_provider_404(authenticated_client) -> None:
    resp = _put_api_key(authenticated_client, "nope", "keyed", ANTHROPIC_KEY)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_provider"


def test_set_api_key_codex_unsupported_400(authenticated_client) -> None:
    resp = _put_api_key(authenticated_client, "codex", "keyed", "sk-proj-test-key-1234")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "api_key_not_supported"


def test_set_api_key_too_short_400(authenticated_client) -> None:
    resp = _put_api_key(authenticated_client, "anthropic", "keyed", "  abc  ")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_api_key"


def test_set_api_key_requires_auth(client) -> None:
    resp = client.put(
        "/v1/auth/anthropic/profiles/keyed/api-key",
        json={"api_key": ANTHROPIC_KEY},
    )
    assert resp.status_code == 401


def test_gemini_profile_api_key_supported(authenticated_client, credential_blobs) -> None:
    account_id = _account_id(authenticated_client)

    resp = _put_api_key(authenticated_client, "gemini-cli", "keyed", "AIzaSyTestKey1234")

    assert resp.status_code == 200, resp.text
    assert resp.json()["auth_type"] == "api_key"
    service = gemini_credential_service_for(credential_name_for(account_id, "keyed"))
    assert json.loads(credential_blobs.read(service, "default"))["api_key"] == "AIzaSyTestKey1234"


def test_delete_api_key_profile_removes_blob(authenticated_client, credential_blobs) -> None:
    account_id = _account_id(authenticated_client)
    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )
    service = credential_service_for(credential_name_for(account_id, "keyed"))
    assert credential_blobs.read(service, "default") is not None

    resp = authenticated_client.delete("/v1/auth/anthropic/profiles/keyed")

    assert resp.status_code == 204
    assert credential_blobs.read(service, "default") is None
    listed = authenticated_client.get("/v1/auth/anthropic/profiles").json()["profiles"]
    assert all(p["name"] != "keyed" for p in listed)


def test_refresh_api_key_profile_is_noop(authenticated_client, credential_blobs) -> None:
    account_id = _account_id(authenticated_client)
    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )

    resp = authenticated_client.post("/v1/auth/anthropic/profiles/keyed/refresh")

    assert resp.status_code == 200
    assert resp.json()["state"] == "authenticated"
    assert resp.json()["auth_type"] == "api_key"
    service = credential_service_for(credential_name_for(account_id, "keyed"))
    assert json.loads(credential_blobs.read(service, "default"))["api_key"] == ANTHROPIC_KEY


def test_refresh_api_key_profile_with_missing_blob_marks_error(
    authenticated_client, credential_blobs
) -> None:
    """Refresh must not report success when the key blob is gone: the
    strategy re-validates the blob and the lifecycle flips ERROR (audit F09)."""
    account_id = _account_id(authenticated_client)
    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )
    service = credential_service_for(credential_name_for(account_id, "keyed"))
    credential_blobs.delete(service, "default")

    resp = authenticated_client.post("/v1/auth/anthropic/profiles/keyed/refresh")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "auth_required"
    status = authenticated_client.get("/v1/auth/anthropic/profiles/keyed/status")
    assert status.json()["state"] == "error"


def test_set_api_key_cancels_pending_oauth_flow(authenticated_client, credential_blobs) -> None:
    """A late OAuth callback (pending TTL 600s) must not overwrite a key that
    was stored after the flow began (audit F10)."""
    account_id = _account_id(authenticated_client)
    authenticated_client.app.state.anthropic_http_factory = _oauth_token_factory()
    start = authenticated_client.post("/v1/auth/anthropic/profiles", json={"name": "keyed"})
    assert start.status_code == 201
    state = start.json()["state"]

    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )

    auth_header = authenticated_client.headers.pop("Authorization")
    try:
        late = authenticated_client.get("/callback", params={"code": "late-code", "state": state})
    finally:
        authenticated_client.headers["Authorization"] = auth_header
    assert late.status_code == 400  # pending state was consumed by the key PUT

    service = credential_service_for(credential_name_for(account_id, "keyed"))
    assert json.loads(credential_blobs.read(service, "default")) == {
        "auth_type": "api_key",
        "api_key": ANTHROPIC_KEY,
    }
    profile = authenticated_client.get("/v1/auth/anthropic/profiles/keyed").json()
    assert profile["auth_type"] == "api_key"
    assert profile["state"] == "authenticated"


def test_oauth_completion_flips_auth_type_back_to_oauth(
    authenticated_client, credential_blobs
) -> None:
    """Re-OAuth of a former api_key profile must flip the discriminator back
    (audit F11), and starting the flow must NOT desync it beforehand (F08)."""
    account_id = _account_id(authenticated_client)
    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )
    authenticated_client.app.state.anthropic_http_factory = _oauth_token_factory()

    start = authenticated_client.post("/v1/auth/anthropic/profiles", json={"name": "keyed"})
    assert start.status_code == 201
    started = authenticated_client.get("/v1/auth/anthropic/profiles/keyed").json()
    # Flow START keeps the api_key identity (only state goes pending) — F08.
    assert started["auth_type"] == "api_key"
    assert started["account_label"] == "API key ····1234"
    assert started["state"] == "pending"

    auth_header = authenticated_client.headers.pop("Authorization")
    try:
        cb = authenticated_client.get(
            "/callback", params={"code": "auth-code", "state": start.json()["state"]}
        )
    finally:
        authenticated_client.headers["Authorization"] = auth_header
    assert cb.status_code == 200

    profile = authenticated_client.get("/v1/auth/anthropic/profiles/keyed").json()
    assert profile["auth_type"] == "oauth"
    assert profile["state"] == "authenticated"
    service = credential_service_for(credential_name_for(account_id, "keyed"))
    assert json.loads(credential_blobs.read(service, "default"))["access_token"] == "oauth-tok"


def test_patch_profile_preserves_api_key_auth_type(authenticated_client) -> None:
    """PATCHing defaults must not reset the discriminator (audit F12)."""
    assert (
        _put_api_key(authenticated_client, "anthropic", "keyed", ANTHROPIC_KEY).status_code == 200
    )

    resp = authenticated_client.patch(
        "/v1/auth/anthropic/profiles/keyed",
        json={"defaults": {"max_tokens": 1024}},
    )

    assert resp.status_code == 200
    assert resp.json()["auth_type"] == "api_key"
    assert resp.json()["defaults"]["max_tokens"] == 1024


def test_legacy_profile_index_defaults_to_oauth_auth_type(
    authenticated_client, credential_blobs
) -> None:
    """Index blobs written before the auth_type field deserialize with the
    'oauth' default — the no-migration-friction constraint."""
    account_id = _account_id(authenticated_client)
    credential_blobs.write(
        "aigateway:index",
        "default",
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "id": f"{account_id}:anthropic:legacy",
                        "account_id": account_id,
                        "provider": "anthropic",
                        "name": "legacy",
                        "state": "authenticated",
                    }
                ],
            }
        ),
    )

    listed = authenticated_client.get("/v1/auth/anthropic/profiles")

    assert listed.status_code == 200
    (profile,) = [p for p in listed.json()["profiles"] if p["name"] == "legacy"]
    assert profile["auth_type"] == "oauth"
