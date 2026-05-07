from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from aigateway.core.credential_store import CredentialStore
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.plugins.anthropic_provider.auth import (
    KEYCHAIN_SERVICE,
    OAUTH_REFRESH_URL,
    AnthropicOAuth,
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


def _wrap(creds: dict) -> str:
    return json.dumps({"claudeAiOauth": creds})


def _fresh_creds(expires_in_ms: int = 3_600_000) -> dict:
    return {
        "accessToken": "tok-fresh",
        "refreshToken": "rt-1",
        "expiresAt": int(time.time() * 1000) + expires_in_ms,
        "scopes": ["user:inference"],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_5x",
    }


def _http_factory(transport: httpx.MockTransport):
    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    return factory


@pytest.mark.asyncio
async def test_missing_credential_raises() -> None:
    strat = AnthropicOAuth(credential_store=_FakeStore(payload=None), account="alice")
    with pytest.raises(CredentialNotFoundError):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_malformed_json_raises_auth_error() -> None:
    strat = AnthropicOAuth(credential_store=_FakeStore(payload="{not json"), account="alice")
    with pytest.raises(AuthError, match="not valid JSON"):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_missing_outer_key_raises() -> None:
    strat = AnthropicOAuth(
        credential_store=_FakeStore(payload=json.dumps({"unrelated": 1})), account="alice"
    )
    with pytest.raises(AuthError, match="claudeAiOauth"):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_fresh_credential_yields_three_headers() -> None:
    creds = _fresh_creds()
    strat = AnthropicOAuth(
        credential_store=_FakeStore(payload=_wrap(creds)),
        account="alice",
    )
    headers = await strat.get_authorization_header()
    assert headers["Authorization"] == "Bearer tok-fresh"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "oauth-2025-04-20" in headers["anthropic-beta"]


@pytest.mark.asyncio
async def test_expired_credential_triggers_refresh() -> None:
    expired = _fresh_creds(expires_in_ms=-1000)
    expired["accessToken"] = "tok-old"

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
                "scope": "user:inference",
            },
        )

    store = _FakeStore(payload=_wrap(expired))
    strat = AnthropicOAuth(
        credential_store=store,
        account="alice",
        http_client_factory=_http_factory(httpx.MockTransport(handler)),
    )

    headers = await strat.get_authorization_header()

    assert headers["Authorization"] == "Bearer tok-new"
    assert captured["url"] == OAUTH_REFRESH_URL
    assert captured["body"]["grant_type"] == "refresh_token"
    assert captured["body"]["refresh_token"] == "rt-1"

    assert len(store.writes) == 1
    written = json.loads(store.writes[0][2])
    assert written["claudeAiOauth"]["accessToken"] == "tok-new"
    assert written["claudeAiOauth"]["refreshToken"] == "rt-2"


@pytest.mark.asyncio
async def test_refresh_endpoint_401_raises() -> None:
    expired = _fresh_creds(expires_in_ms=-1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    strat = AnthropicOAuth(
        credential_store=_FakeStore(payload=_wrap(expired)),
        account="alice",
        http_client_factory=_http_factory(httpx.MockTransport(handler)),
    )
    with pytest.raises(AuthError, match="401"):
        await strat.get_authorization_header()


@pytest.mark.asyncio
async def test_invalidate_drops_cache() -> None:
    creds = _fresh_creds()
    strat = AnthropicOAuth(
        credential_store=_FakeStore(payload=_wrap(creds)),
        account="alice",
    )
    await strat.get_authorization_header()
    assert strat._cached is not None
    await strat.invalidate()
    assert strat._cached is None


@pytest.mark.asyncio
async def test_keychain_service_constant() -> None:
    """SF-77 spike: Claude Code uses this exact keychain service name. Don't change."""
    assert KEYCHAIN_SERVICE == "Claude Code-credentials"
