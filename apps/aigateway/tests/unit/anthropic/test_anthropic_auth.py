from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from aigateway.core.credential_store import CredentialStore
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.plugins.anthropic_provider.auth import (
    AnthropicOAuth,
    keychain_service_for,
)
from aigateway.plugins.anthropic_provider.oauth_config import (
    ANTHROPIC_REFRESH_SCOPES,
    ANTHROPIC_TOKEN_URL,
)


class _FakeStore(CredentialStore):
    def __init__(self, payload: str | None = None) -> None:
        self.payload = payload
        self.writes: list[tuple[str, str, str]] = []

    def read(self, service: str, account: str) -> str | None:
        return self.payload

    def write(self, service: str, account: str, value: str) -> None:
        self.writes.append((service, account, value))
        self.payload = value

    def delete(self, service: str, account: str) -> None:
        self.payload = None


def _wrap(creds: dict) -> str:
    """Token payload as stored in aigateway:anthropic:<name>."""
    return json.dumps(creds)


def _fresh_creds(expires_in_ms: int = 3_600_000) -> dict:
    return {
        "access_token": "tok-fresh",
        "refresh_token": "rt-1",
        "expires_at_ms": int(time.time() * 1000) + expires_in_ms,
        "token_type": "Bearer",
    }


def _http_factory(transport: httpx.MockTransport):
    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    return factory


@pytest.mark.asyncio
async def test_keychain_service_uses_aigateway_namespace() -> None:
    """Profiles are stored under aigateway:anthropic:<name>."""
    assert keychain_service_for("default") == "aigateway:anthropic:default"
    assert keychain_service_for("work") == "aigateway:anthropic:work"


@pytest.mark.asyncio
async def test_missing_credential_raises() -> None:
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=_FakeStore(payload=None),
    )
    with pytest.raises(CredentialNotFoundError):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_malformed_json_raises_auth_error() -> None:
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=_FakeStore(payload="{not json"),
    )
    with pytest.raises(AuthError, match="not valid JSON"):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_missing_required_field_raises() -> None:
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=_FakeStore(payload=json.dumps({"access_token": "t"})),
    )
    with pytest.raises(AuthError, match="missing required field"):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_fresh_credential_yields_three_headers() -> None:
    creds = _fresh_creds()
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=_FakeStore(payload=_wrap(creds)),
    )
    headers = await strat.get_authorization_header()
    assert headers["Authorization"] == "Bearer tok-fresh"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "oauth-2025-04-20" in headers["anthropic-beta"]


@pytest.mark.asyncio
async def test_expired_credential_triggers_refresh() -> None:
    expired = _fresh_creds(expires_in_ms=-1000)
    expired["access_token"] = "tok-old"

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "access_token": "tok-new",
                "refresh_token": "rt-2",
                "expires_in": 3600,
            },
        )

    store = _FakeStore(payload=_wrap(expired))
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=store,
        http_client_factory=_http_factory(httpx.MockTransport(handler)),
    )
    headers = await strat.get_authorization_header()

    assert headers["Authorization"] == "Bearer tok-new"
    assert captured["url"] == ANTHROPIC_TOKEN_URL
    assert captured["body"]["grant_type"] == "refresh_token"
    assert captured["body"]["refresh_token"] == "rt-1"
    assert captured["body"]["scope"] == " ".join(ANTHROPIC_REFRESH_SCOPES)

    assert len(store.writes) == 1
    written = json.loads(store.writes[0][2])
    assert written["access_token"] == "tok-new"
    assert written["refresh_token"] == "rt-2"


@pytest.mark.asyncio
async def test_refresh_endpoint_401_raises() -> None:
    expired = _fresh_creds(expires_in_ms=-1000)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=_FakeStore(payload=_wrap(expired)),
        http_client_factory=_http_factory(httpx.MockTransport(handler)),
    )
    with pytest.raises(AuthError, match="401"):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_invalidate_drops_cache() -> None:
    creds = _fresh_creds()
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=_FakeStore(payload=_wrap(creds)),
    )
    await strat.get_authorization_header()
    assert strat._cached is not None
    await strat.invalidate()
    assert strat._cached is None


@pytest.mark.asyncio
async def test_persist_credentials_persists_and_caches() -> None:
    """persist_credentials() writes to store + populates cache after OAuth callback."""
    store = _FakeStore(payload=None)
    strat = AnthropicOAuth(
        profile_name="default",
        credential_store=store,
    )
    fresh = _fresh_creds()
    strat.persist_credentials(fresh)

    headers = await strat.get_authorization_header()
    assert headers["Authorization"] == f"Bearer {fresh['access_token']}"
    assert len(store.writes) == 1
    written = json.loads(store.writes[0][2])
    assert written["access_token"] == fresh["access_token"]


@pytest.mark.asyncio
async def test_keychain_service_constant() -> None:
    """Don't change without coordinating with Electron."""
    strat = AnthropicOAuth(profile_name="work", credential_store=_FakeStore())
    assert strat.keychain_service() == "aigateway:anthropic:work"
    assert strat.keychain_account() == "default"
