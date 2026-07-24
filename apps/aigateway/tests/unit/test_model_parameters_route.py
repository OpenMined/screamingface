"""Phase 3 (OME-479): GET /v1/model-parameters — profile-bound detailed contract.

Exercises the real app/registry so the endpoint is proven end-to-end WITHOUT
hardcoding any provider inventory: canonical-id lookup, reuse of the existing
account/profile/auth resolution, caller-declared auth being impossible, the
private/no-store + Vary headers, deterministic revision-sensitive opaque IDs,
and non-exposure of account identity or secrets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    AuthType,
    Profile,
    ProfileState,
    profile_id_for,
)

_MODEL = "anthropic/claude-opus-4-8"


def _account_id(client: TestClient) -> str:
    return client.get("/v1/auth/me").json()["id"]


async def _seed_profile(credential_blobs, account_id: str, *, auth_type: AuthType) -> None:
    # The detailed contract only needs the profile RECORD (auth mode + state) —
    # it never injects a credential — so no credential blob is written here.
    idx = ProfileIndexStore(credential_store=credential_blobs.store)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            auth_type=auth_type,
        )
    )


def _get(client: TestClient, model: str = _MODEL, **params: str):
    return client.get("/v1/model-parameters", params={"model": model, **params})


@pytest.mark.asyncio
async def test_returns_locked_headers_and_v1_envelope(credential_blobs, authenticated_client):
    account_id = _account_id(authenticated_client)
    await _seed_profile(credential_blobs, account_id, auth_type="api_key")

    resp = _get(authenticated_client)
    assert resp.status_code == 200, resp.text
    # Locked cache/vary headers: a profile-bound contract must never be shared.
    assert resp.headers["cache-control"] == "private, no-store"
    vary = resp.headers["vary"]
    assert "Authorization" in vary and "X-Profile" in vary

    body = resp.json()
    assert body["schema_version"] == 1
    assert body["contract_id"].startswith("pc_")
    assert body["model"]["id"] == _MODEL
    assert body["model"]["gateway_provider"] == "anthropic"
    assert body["model"]["upstream_id"] == "claude-opus-4-8"
    assert body["context"]["scope"] == "account_profile"
    assert body["context"]["auth_mode"] == "api_key"
    assert body["context"]["revision"].startswith("ctx_")
    for section in ("parameters", "tools", "transport"):
        assert isinstance(body[section], dict)


def test_unprefixed_model_is_rejected(authenticated_client):
    # A bare id with no provider segment cannot be routed to a plugin: the
    # provider is selected SOLELY by the canonical prefix, never guessed.
    resp = _get(authenticated_client, model="claude-opus-4-8")
    assert resp.status_code == 400
    assert "provider-prefixed" in resp.json()["detail"]


def test_unknown_provider_is_rejected(authenticated_client):
    # Distinct from the unprefixed case: a slash IS present, but no plugin owns
    # that prefix, so the registry lookup — not the prefix check — rejects it.
    resp = _get(authenticated_client, model="bogus/whatever")
    assert resp.status_code == 400
    assert "unknown provider" in resp.json()["detail"]


def test_unknown_model_under_known_provider_is_rejected_before_profile(authenticated_client):
    # cross-provider / non-existent id fails as model_not_found, and does so
    # BEFORE any profile resolution (no profile is seeded here).
    resp = _get(authenticated_client, model="anthropic/not-a-real-model")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "model_not_found"


def test_missing_profile_reuses_chat_credential_resolution(authenticated_client):
    # anthropic is not chatless, so with no profile the endpoint raises the SAME
    # 404 the chat route raises — proving the resolution is reused, not reinvented.
    resp = _get(authenticated_client)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


@pytest.mark.asyncio
async def test_auth_mode_is_derived_from_profile_not_caller_declared(
    credential_blobs, authenticated_client
):
    account_id = _account_id(authenticated_client)
    await _seed_profile(credential_blobs, account_id, auth_type="oauth")

    # A caller-supplied auth_type query param must be ignored entirely.
    resp = _get(authenticated_client, auth_type="api_key")
    assert resp.status_code == 200, resp.text
    assert resp.json()["context"]["auth_mode"] == "oauth"


@pytest.mark.asyncio
async def test_contract_id_is_deterministic_and_changes_with_auth_mode(
    credential_blobs, authenticated_client
):
    account_id = _account_id(authenticated_client)

    await _seed_profile(credential_blobs, account_id, auth_type="api_key")
    first = _get(authenticated_client).json()["contract_id"]
    again = _get(authenticated_client).json()["contract_id"]
    assert first == again  # deterministic for identical context

    await _seed_profile(credential_blobs, account_id, auth_type="oauth")  # re-key same profile
    after = _get(authenticated_client).json()["contract_id"]
    assert after != first  # auth-mode change is a relevant revision change


@pytest.mark.asyncio
async def test_response_never_exposes_account_id_or_secrets(credential_blobs, authenticated_client):
    account_id = _account_id(authenticated_client)
    await _seed_profile(credential_blobs, account_id, auth_type="api_key")

    resp = _get(authenticated_client)
    assert resp.status_code == 200, resp.text
    # opaque IDs are one-way: the account id (a digest input) never appears raw.
    assert account_id not in resp.text
