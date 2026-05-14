from __future__ import annotations

import httpx
import pytest

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)


@pytest.fixture
def client_with_index(authenticated_client, fake_keychain):
    return authenticated_client, fake_keychain


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def test_list_profiles_empty(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get("/v1/auth/profiles")
    assert resp.status_code == 200
    assert resp.json() == {"profiles": []}


@pytest.mark.asyncio
async def test_list_profiles_returns_seeded(fake_keychain, authenticated_client) -> None:
    account_id = _account_id(authenticated_client)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5"),
        )
    )

    resp = authenticated_client.get("/v1/auth/profiles")
    body = resp.json()
    assert resp.status_code == 200
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["id"] == profile_id_for(account_id, "anthropic", "default")
    assert body["profiles"][0]["account_id"] == account_id
    assert "access_token" not in str(body)


def test_get_profile_404_on_missing(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get("/v1/auth/anthropic/profiles/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_start_oauth_returns_authorize_url(client_with_index) -> None:
    client, _ = client_with_index
    account_id = _account_id(client)
    resp = client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["profile_id"] == profile_id_for(account_id, "anthropic", "work")
    assert body["authorize_url"].startswith("https://claude.ai/oauth/authorize")
    assert "state=" in body["authorize_url"]
    assert "code_challenge=" in body["authorize_url"]
    assert "code_challenge_method=S256" in body["authorize_url"]
    # Required by the public Claude Code OAuth app to surface the consent screen
    assert "code=true" in body["authorize_url"]
    # Full Claude Code scope set so the issued token is treated as a user-OAuth
    # token rather than an API token.
    assert "user%3Asessions%3Aclaude_code" in body["authorize_url"]
    assert "org%3Acreate_api_key" in body["authorize_url"]
    # redirect_uri must be http://localhost:*/callback (not 127.0.0.1 and not
    # a per-provider path) — the public Claude Code OAuth client only allows
    # this canonical shape.
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A" in body["authorize_url"]
    assert "%2Fcallback&" in body["authorize_url"]


def test_top_level_callback_dispatches_by_state(client_with_index) -> None:
    """The /callback route looks up the provider from the pending-auth
    state, so the same path serves every provider — matching what claude.ai
    accepts as a redirect_uri."""
    client, _ = client_with_index
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "topcb"})
    state = start.json()["state"]

    auth_header = client.headers.pop("Authorization")
    try:
        resp = client.get(
            "/callback",
            params={"code": "auth-code-top", "state": state},
            follow_redirects=False,
        )
    finally:
        client.headers["Authorization"] = auth_header
    assert resp.status_code == 200
    prof = client.get("/v1/auth/anthropic/profiles/topcb").json()
    assert prof["state"] == "authenticated"


def test_top_level_callback_unknown_state_400(client_with_index) -> None:
    client, _ = client_with_index
    auth_header = client.headers.pop("Authorization")
    try:
        resp = client.get("/callback", params={"code": "x", "state": "never-issued"})
    finally:
        client.headers["Authorization"] = auth_header
    assert resp.status_code == 400


def test_start_oauth_for_unknown_provider_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post("/v1/auth/ghost/profiles", json={"name": "x"})
    assert resp.status_code == 404


class _NoOAuthPlugin:
    custom_llm_provider = "local"

    def register_models(self) -> list:
        return []

    def oauth_config(self):
        return None


def test_start_oauth_for_non_oauth_provider_400(client_with_index) -> None:
    client, _ = client_with_index
    client.app.state.providers._plugins["local"] = _NoOAuthPlugin()

    resp = client.post("/v1/auth/local/profiles", json={"name": "x"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "provider_does_not_use_oauth"


def test_start_oauth_creates_pending_profile(client_with_index) -> None:
    client, _ = client_with_index
    client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    resp = client.get("/v1/auth/anthropic/profiles/work")
    assert resp.status_code == 200
    assert resp.json()["state"] == "pending"


def test_profiles_are_scoped_to_current_account(
    client_with_index, provisioned_user_factory
) -> None:
    client, _ = client_with_index
    admin_account_id = _account_id(client)
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "admin-owned"})
    assert start.status_code == 201

    provisioned_user_factory("bob", "bob-pass1")
    login = client.post("/v1/auth/login", json={"username": "bob", "password": "bob-pass1"})
    bob_token = login.json()["token"]
    client.headers.update({"Authorization": f"Bearer {bob_token}"})

    listing = client.get("/v1/auth/profiles")
    assert listing.status_code == 200
    assert listing.json() == {"profiles": []}
    assert client.get("/v1/auth/anthropic/profiles/admin-owned").status_code == 404
    assert (
        profile_id_for(admin_account_id, "anthropic", "admin-owned") == start.json()["profile_id"]
    )


@pytest.mark.asyncio
async def test_list_provider_profiles_returns_only_current_account(
    fake_keychain, authenticated_client, provisioned_user_factory
) -> None:
    admin_account_id = _account_id(authenticated_client)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(admin_account_id, "anthropic", "admin-owned"),
            account_id=admin_account_id,
            provider="anthropic",
            name="admin-owned",
            state=ProfileState.AUTHENTICATED,
        )
    )
    provisioned_user_factory("bob", "bob-pass1")
    login = authenticated_client.post(
        "/v1/auth/login", json={"username": "bob", "password": "bob-pass1"}
    )
    bob_token = login.json()["token"]
    authenticated_client.headers.update({"Authorization": f"Bearer {bob_token}"})

    resp = authenticated_client.get("/v1/auth/anthropic/profiles")
    assert resp.status_code == 200
    assert resp.json() == {"profiles": []}


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("GET", "/v1/auth/profiles", None),
        ("GET", "/v1/auth/anthropic/profiles", None),
        ("GET", "/v1/auth/anthropic/profiles/default", None),
        ("POST", "/v1/auth/anthropic/profiles", {"name": "default"}),
        ("POST", "/v1/auth/anthropic/exchange-code", {"code": "x", "state": "y"}),
        ("GET", "/v1/auth/anthropic/profiles/default/status", None),
        ("PATCH", "/v1/auth/anthropic/profiles/default", {"account_label": "x"}),
        ("DELETE", "/v1/auth/anthropic/profiles/default", None),
        ("POST", "/v1/auth/anthropic/profiles/default/refresh", None),
    ],
)
def test_oauth_profile_routes_require_jwt(client, method, path, json) -> None:
    response = client.request(method, path, json=json)
    assert response.status_code == 401


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


def _failing_token_factory():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(400, json={"error": "invalid_grant"})
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


def _html_failing_token_factory():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(400, text="<script>alert('x')</script>")
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


def test_callback_completes_auth(client_with_index) -> None:
    client, fake_keychain = client_with_index
    account_id = _account_id(client)
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    state = start.json()["state"]

    auth_header = client.headers.pop("Authorization")
    try:
        cb = client.get(
            "/v1/auth/anthropic/callback",
            params={"code": "auth-code-1", "state": state},
            follow_redirects=False,
        )
    finally:
        client.headers["Authorization"] = auth_header
    assert cb.status_code == 200

    prof = client.get("/v1/auth/anthropic/profiles/work").json()
    assert prof["state"] == "authenticated"

    from aigateway.plugins.anthropic_provider.auth import keychain_service_for

    blob = fake_keychain.read(
        keychain_service_for(credential_name_for(account_id, "work")), "default"
    )
    assert "new-tok" in blob


def test_callback_exchange_failure_keeps_pending_state(client_with_index) -> None:
    client, _ = client_with_index
    client.app.state.anthropic_http_factory = _failing_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "retry"})
    state = start.json()["state"]

    auth_header = client.headers.pop("Authorization")
    try:
        failed = client.get(
            "/callback",
            params={"code": "bad-code", "state": state},
            follow_redirects=False,
        )
        client.app.state.anthropic_http_factory = _mock_token_factory()
        retried = client.get(
            "/callback",
            params={"code": "good-code", "state": state},
            follow_redirects=False,
        )
    finally:
        client.headers["Authorization"] = auth_header

    assert failed.status_code == 500
    assert retried.status_code == 200
    prof = client.get("/v1/auth/anthropic/profiles/retry").json()
    assert prof["state"] == "authenticated"


def test_callback_error_html_escapes_provider_response(client_with_index) -> None:
    client, _ = client_with_index
    client.app.state.anthropic_http_factory = _html_failing_token_factory()
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "htmlfail"})
    state = start.json()["state"]

    auth_header = client.headers.pop("Authorization")
    try:
        resp = client.get(
            "/callback",
            params={"code": "bad-code", "state": state},
            follow_redirects=False,
        )
    finally:
        client.headers["Authorization"] = auth_header

    assert resp.status_code == 500
    assert "<script>" not in resp.text
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in resp.text


def test_callback_with_unknown_state_400(client_with_index) -> None:
    client, _ = client_with_index
    auth_header = client.headers.pop("Authorization")
    try:
        resp = client.get(
            "/v1/auth/anthropic/callback",
            params={"code": "x", "state": "never-issued"},
        )
    finally:
        client.headers["Authorization"] = auth_header
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


def test_exchange_code_runs_oauth(client_with_index) -> None:
    """POST /v1/auth/{provider}/exchange-code completes auth same as GET callback."""
    client, fake_keychain = client_with_index
    account_id = _account_id(client)
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "paste"})
    state = start.json()["state"]

    resp = client.post(
        "/v1/auth/anthropic/exchange-code",
        json={"code": "pasted-code-1", "state": state},
    )
    assert resp.status_code == 200
    assert resp.json() == {"state": "authenticated"}

    prof = client.get("/v1/auth/anthropic/profiles/paste").json()
    assert prof["state"] == "authenticated"

    from aigateway.plugins.anthropic_provider.auth import keychain_service_for

    blob = fake_keychain.read(
        keychain_service_for(credential_name_for(account_id, "paste")), "default"
    )
    assert "new-tok" in blob


def test_exchange_code_with_unknown_state_400(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post(
        "/v1/auth/anthropic/exchange-code",
        json={"code": "x", "state": "never-issued"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_state"


def test_exchange_code_with_unknown_provider_404(client_with_index) -> None:
    client, _ = client_with_index
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "mismatch"})

    resp = client.post(
        "/v1/auth/ghost/exchange-code",
        json={"code": "x", "state": start.json()["state"]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_provider"


def test_exchange_code_with_other_accounts_state_404(
    client_with_index, provisioned_user_factory
) -> None:
    client, _ = client_with_index
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "admin-only"})
    provisioned_user_factory("bob", "bob-pass1")
    login = client.post("/v1/auth/login", json={"username": "bob", "password": "bob-pass1"})
    client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})

    resp = client.post(
        "/v1/auth/anthropic/exchange-code",
        json={"code": "x", "state": start.json()["state"]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_status_404_on_missing_profile(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get("/v1/auth/anthropic/profiles/missing/status")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_patch_404_on_missing_profile(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.patch(
        "/v1/auth/anthropic/profiles/missing",
        json={"account_label": "user@example.com"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_patch_updates_account_label(client_with_index) -> None:
    client, _ = client_with_index
    client.post("/v1/auth/anthropic/profiles", json={"name": "label"})

    resp = client.patch(
        "/v1/auth/anthropic/profiles/label",
        json={"account_label": "user@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["account_label"] == "user@example.com"


def test_delete_unknown_provider_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.delete("/v1/auth/ghost/profiles/default")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_provider"


def test_delete_missing_profile_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.delete("/v1/auth/anthropic/profiles/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_refresh_unknown_provider_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post("/v1/auth/ghost/profiles/default/refresh")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_provider"


def test_refresh_missing_profile_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post("/v1/auth/anthropic/profiles/missing/refresh")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_delete_removes_profile_and_tokens(client_with_index) -> None:
    client, fake_keychain = client_with_index
    account_id = _account_id(client)
    client.app.state.anthropic_http_factory = _mock_token_factory()

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "z"})
    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": start.json()["state"]})

    from aigateway.plugins.anthropic_provider.auth import keychain_service_for

    assert (
        fake_keychain.read(keychain_service_for(credential_name_for(account_id, "z")), "default")
        is not None
    )

    resp = client.delete("/v1/auth/anthropic/profiles/z")
    assert resp.status_code == 204
    assert (
        fake_keychain.read(keychain_service_for(credential_name_for(account_id, "z")), "default")
        is None
    )
    g = client.get("/v1/auth/anthropic/profiles/z")
    assert g.status_code == 404
