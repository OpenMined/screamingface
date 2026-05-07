from __future__ import annotations

import httpx
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


def test_start_oauth_returns_authorize_url(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["profile_id"] == "anthropic:work"
    assert body["authorize_url"].startswith("https://console.anthropic.com/oauth/authorize")
    assert "state=" in body["authorize_url"]
    assert "code_challenge=" in body["authorize_url"]
    assert "code_challenge_method=S256" in body["authorize_url"]


def test_start_oauth_for_unknown_provider_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post("/v1/auth/ghost/profiles", json={"name": "x"})
    assert resp.status_code == 404


def test_start_oauth_creates_pending_profile(client_with_index) -> None:
    client, _ = client_with_index
    client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    resp = client.get("/v1/auth/anthropic/profiles/work")
    assert resp.status_code == 200
    assert resp.json()["state"] == "pending"


def _mock_token_factory():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "access_token": "new-tok",
                "refresh_token": "new-rt",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


def test_callback_completes_auth(client_with_index) -> None:
    client, fake_keychain = client_with_index
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    state = start.json()["state"]

    cb = client.get(
        "/v1/auth/anthropic/callback",
        params={"code": "auth-code-1", "state": state},
        follow_redirects=False,
    )
    assert cb.status_code == 200

    prof = client.get("/v1/auth/anthropic/profiles/work").json()
    assert prof["state"] == "authenticated"

    from aigateway.plugins.anthropic_provider.auth import keychain_service_for

    blob = fake_keychain.read(keychain_service_for("work"), "default")
    assert "new-tok" in blob


def test_callback_with_unknown_state_400(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get(
        "/v1/auth/anthropic/callback",
        params={"code": "x", "state": "never-issued"},
    )
    assert resp.status_code == 400


def test_status_returns_pending_then_authenticated(client_with_index) -> None:
    client, _ = client_with_index
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "x"})
    state = start.json()["state"]

    s1 = client.get("/v1/auth/anthropic/profiles/x/status").json()
    assert s1["state"] == "pending"

    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": state})

    s2 = client.get("/v1/auth/anthropic/profiles/x/status").json()
    assert s2["state"] == "authenticated"


def test_patch_updates_defaults(client_with_index) -> None:
    client, _ = client_with_index
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "y"})
    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": start.json()["state"]})

    resp = client.patch(
        "/v1/auth/anthropic/profiles/y",
        json={"defaults": {"model": "anthropic/claude-opus-4-7", "max_tokens": 8192}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["defaults"]["model"] == "anthropic/claude-opus-4-7"
    assert body["defaults"]["max_tokens"] == 8192


def test_delete_removes_profile_and_tokens(client_with_index) -> None:
    client, fake_keychain = client_with_index
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "z"})
    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": start.json()["state"]})

    from aigateway.plugins.anthropic_provider.auth import keychain_service_for

    assert fake_keychain.read(keychain_service_for("z"), "default") is not None

    resp = client.delete("/v1/auth/anthropic/profiles/z")
    assert resp.status_code == 204
    assert fake_keychain.read(keychain_service_for("z"), "default") is None
    g = client.get("/v1/auth/anthropic/profiles/z")
    assert g.status_code == 404
