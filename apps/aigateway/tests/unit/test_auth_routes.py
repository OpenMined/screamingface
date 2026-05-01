from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState
from aigateway.main import create_app


@pytest.fixture
def client_with_index(fake_keychain, monkeypatch):
    """Patch the global credential store factory so create_app() picks up our fake."""
    from aigateway.core import bootstrap as bs_module
    from aigateway.core import credential_store as cs_module
    from aigateway.core import profile_index as pi_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(pi_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: fake_keychain)

    app = create_app()
    return TestClient(app), fake_keychain


def test_list_profiles_empty(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get("/v1/auth/profiles")
    assert resp.status_code == 200
    assert resp.json() == {"profiles": []}


@pytest.mark.asyncio
async def test_list_profiles_returns_seeded(fake_keychain, monkeypatch) -> None:
    from aigateway.core import bootstrap as bs_module
    from aigateway.core import credential_store as cs_module
    from aigateway.core import profile_index as pi_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(pi_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: fake_keychain)

    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id="anthropic:default",
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5"),
        )
    )

    app = create_app()
    client = TestClient(app)

    resp = client.get("/v1/auth/profiles")
    body = resp.json()
    assert resp.status_code == 200
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["id"] == "anthropic:default"
    assert "access_token" not in str(body)


def test_get_profile_404_on_missing(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get("/v1/auth/anthropic/profiles/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"
