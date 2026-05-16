from __future__ import annotations

import asyncio
import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException

from aigateway.core.plugin_base import OAuthCodeExchangeRequest, OAuthConfig
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from aigateway.plugins.codex_provider.oauth_config import CODEX_CLIENT_ID
from aigateway.routes.auth import _complete_oauth_for_app


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
    parsed = urlparse(body["authorize_url"])
    assert body["profile_id"] == profile_id_for(account_id, "anthropic", "work")
    assert parsed.scheme == "https"
    assert parsed.netloc == "claude.com"
    assert parsed.path == "/cai/oauth/authorize"
    assert "state=" in body["authorize_url"]
    assert "code_challenge=" in body["authorize_url"]
    assert "code_challenge_method=S256" in body["authorize_url"]
    # Required by the public Claude Code OAuth app to surface the consent screen
    assert "code=true" in body["authorize_url"]
    # Claude subscription OAuth must request the user scope set, not
    # org:create_api_key, otherwise the flow is routed toward Console/API-key
    # billing rather than Claude subscription capacity.
    assert "user%3Asessions%3Aclaude_code" in body["authorize_url"]
    assert "org%3Acreate_api_key" not in body["authorize_url"]
    # redirect_uri must be http://localhost:*/callback (not 127.0.0.1 and not
    # a per-provider path) — the public Claude Code OAuth client only allows
    # this canonical shape.
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A" in body["authorize_url"]
    assert "%2Fcallback&" in body["authorize_url"]


def test_start_oauth_for_codex_returns_openai_authorize_url(client_with_index) -> None:
    client, _ = client_with_index
    account_id = _account_id(client)

    resp = client.post("/v1/auth/codex/profiles", json={"name": "work"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["profile_id"] == profile_id_for(account_id, "codex", "work")
    parsed = urlparse(body["authorize_url"])
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.openai.com"
    assert parsed.path == "/oauth/authorize"
    assert query["client_id"] == [CODEX_CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"][0] in {
        "http://localhost:1455/auth/callback",
        "http://localhost:1457/auth/callback",
    }
    assert "offline_access" in query["scope"][0].split()
    assert "api.connectors.invoke" in query["scope"][0].split()
    assert query["id_token_add_organizations"] == ["true"]
    assert query["codex_cli_simplified_flow"] == ["true"]
    assert query["originator"] == ["codex_cli_rs"]

    profile = client.get("/v1/auth/codex/profiles/work").json()
    assert profile["state"] == "pending"
    assert "offline_access" in profile["scopes"]


def test_top_level_callback_dispatches_by_state(client_with_index) -> None:
    """The /callback route looks up the provider from the pending-auth
    state, so the same path serves every provider — matching what Claude Code
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


class _RecordingStrategy:
    def __init__(self) -> None:
        self.creds: dict | None = None

    async def get_authorization_header(self) -> dict[str, str]:
        return {}

    def set_credentials(self, creds: dict) -> None:
        self.creds = creds


class _GenericOAuthPlugin:
    custom_llm_provider = "generic"

    def __init__(self) -> None:
        self.strategy = _RecordingStrategy()
        self.exchange_request: OAuthCodeExchangeRequest | None = None

    def register_models(self) -> list:
        return []

    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            authorize_url="https://example.test/oauth/authorize",
            token_url="https://example.test/oauth/token",
            client_id="client-id",
            scopes=["scope-a", "scope-b"],
            redirect_path="/callback",
            extra_authorize_params={"extra": "1"},
        )

    def oauth_strategy_for(self, _profile_name: str) -> _RecordingStrategy:
        return self.strategy

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict:
        self.exchange_request = request
        return {
            "access_token": "generic-token",
            "refresh_token": "generic-refresh",
            "expires_at_ms": 9999999999999,
            "token_type": "Bearer",
        }


class _DelayedOAuthPlugin(_GenericOAuthPlugin):
    def __init__(self) -> None:
        super().__init__()
        self.exchange_count = 0

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict:
        self.exchange_count += 1
        await asyncio.sleep(0.01)
        return await super().exchange_oauth_code(request)


def test_start_oauth_for_non_oauth_provider_400(client_with_index) -> None:
    client, _ = client_with_index
    client.app.state.providers._plugins["local"] = _NoOAuthPlugin()

    resp = client.post("/v1/auth/local/profiles", json={"name": "x"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "provider_does_not_use_oauth"


def test_exchange_code_uses_provider_exchange_hook(client_with_index) -> None:
    client, _ = client_with_index
    account_id = _account_id(client)
    plugin = _GenericOAuthPlugin()
    client.app.state.providers._plugins["generic"] = plugin

    start = client.post("/v1/auth/generic/profiles", json={"name": "work"})
    assert start.status_code == 201
    start_body = start.json()
    query = parse_qs(urlparse(start_body["authorize_url"]).query)
    redirect_uri = query["redirect_uri"][0]

    resp = client.post(
        "/v1/auth/generic/exchange-code",
        json={"code": "generic-code", "state": start_body["state"]},
    )

    assert resp.status_code == 200
    assert plugin.exchange_request is not None
    assert plugin.exchange_request.code == "generic-code"
    assert plugin.exchange_request.redirect_uri == redirect_uri
    assert plugin.exchange_request.state == start_body["state"]
    assert plugin.strategy.creds is not None
    assert plugin.strategy.creds["access_token"] == "generic-token"
    profile = client.get("/v1/auth/generic/profiles/work").json()
    assert profile["id"] == profile_id_for(account_id, "generic", "work")
    assert profile["state"] == "authenticated"


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


def _jwt(payload: dict) -> str:
    def encode(value: dict | bytes) -> str:
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.{encode(b'sig')}"


def _mock_codex_token_factory():
    token_payload = {
        "sub": "sub-1",
        "email": "user@example.com",
        "exp": int(time.time()) + 3600,
        "https://api.openai.com/auth": {"chatgpt_account_id": "acct-1"},
    }
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "access_token": _jwt(token_payload),
                "refresh_token": "codex-refresh",
                "id_token": _jwt(token_payload),
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


def test_codex_nested_callback_completes_auth_with_provider_hook(client_with_index) -> None:
    client, fake_keychain = client_with_index
    account_id = _account_id(client)
    client.app.state.codex_http_factory = _mock_codex_token_factory()

    start = client.post("/v1/auth/codex/profiles", json={"name": "work"})
    state = start.json()["state"]

    auth_header = client.headers.pop("Authorization")
    try:
        cb = client.get(
            "/auth/callback",
            params={"code": "codex-code-1", "state": state},
            follow_redirects=False,
        )
    finally:
        client.headers["Authorization"] = auth_header
    assert cb.status_code == 200

    prof = client.get("/v1/auth/codex/profiles/work").json()
    assert prof["state"] == "authenticated"
    assert prof["account_label"] == "user@example.com"

    from aigateway.plugins.codex_provider.auth import keychain_service_for

    blob = fake_keychain.read(
        keychain_service_for(credential_name_for(account_id, "work")), "default"
    )
    assert blob is not None
    assert json.loads(blob)["refresh_token"] == "codex-refresh"


def test_codex_import_profile_endpoint_is_absent(client_with_index) -> None:
    client, _ = client_with_index

    resp = client.post("/v1/auth/codex/profiles/import", json={"name": "default"})

    assert resp.status_code == 405


def test_callback_exchange_failure_consumes_state_and_marks_profile_error(
    client_with_index,
) -> None:
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
    assert retried.status_code == 400
    prof = client.get("/v1/auth/anthropic/profiles/retry").json()
    assert prof["state"] == "error"


@pytest.mark.asyncio
async def test_complete_oauth_consumes_state_before_awaiting_exchange(client_with_index) -> None:
    client, _ = client_with_index
    account_id = _account_id(client)
    plugin = _DelayedOAuthPlugin()
    client.app.state.providers._plugins["generic"] = plugin

    start = client.post("/v1/auth/generic/profiles", json={"name": "race"})
    state = start.json()["state"]

    results = await asyncio.gather(
        _complete_oauth_for_app(client.app, "generic", "code-one", state, account_id),
        _complete_oauth_for_app(client.app, "generic", "code-two", state, account_id),
        return_exceptions=True,
    )

    assert sum(result is None for result in results) == 1
    errors = [result for result in results if isinstance(result, HTTPException)]
    assert len(errors) == 1
    assert errors[0].status_code == 400
    assert plugin.exchange_count == 1
    prof = client.get("/v1/auth/generic/profiles/race").json()
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


def test_exchange_code_with_provider_mismatch_400(client_with_index) -> None:
    client, _ = client_with_index
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "mismatch"})

    resp = client.post(
        "/v1/auth/ghost/exchange-code",
        json={"code": "x", "state": start.json()["state"]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "provider_mismatch"


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
