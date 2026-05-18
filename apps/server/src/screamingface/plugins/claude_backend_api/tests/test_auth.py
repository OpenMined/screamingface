"""Unit tests for claude-backend-api ClaudeCodeOAuth.

All tests mock the credential store and the httpx client so they run
in milliseconds and are fully hermetic. No real Keychain reads, no
real network calls.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.claude_backend_api.auth import (
    ANTHROPIC_BETA,
    ANTHROPIC_VERSION,
    KEYCHAIN_SERVICE,
    OAUTH_CLIENT_ID,
    OAUTH_REFRESH_SCOPES,
    OAUTH_REFRESH_URL,
    REFRESH_WINDOW_SECONDS,
    ClaudeCodeOAuth,
)
from screamingface.plugins.llm_base.credential_store import CredentialStore
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError

# ----------------------------------------------------------------------------
# Fixtures and helpers
# ----------------------------------------------------------------------------


class FakeCredentialStore(CredentialStore):
    """In-memory credential store fake for tests."""

    def __init__(self, initial: dict[tuple[str, str], str] | None = None) -> None:
        self._store = dict(initial or {})
        self.read_calls: list[tuple[str, str]] = []
        self.write_calls: list[tuple[str, str, str]] = []

    def read(self, service: str, account: str) -> str | None:
        self.read_calls.append((service, account))
        return self._store.get((service, account))

    def write(self, service: str, account: str, value: str) -> None:
        self.write_calls.append((service, account, value))
        self._store[(service, account)] = value


def _fresh_creds(seconds_from_now: float = 3600) -> dict:
    """Build a valid in-keychain credential with a chosen expiry offset."""
    return {
        "accessToken": "sk-ant-oat01-CURRENT_ACCESS",
        "refreshToken": "sk-ant-ort01-CURRENT_REFRESH",
        "expiresAt": int((time.time() + seconds_from_now) * 1000),
        "scopes": ["user:inference", "user:profile"],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_5x",
    }


def _keychain_value(creds: dict) -> str:
    """Wrap a credential dict in the claudeAiOauth envelope and JSON-encode."""
    return json.dumps({"claudeAiOauth": creds})


def _refresh_response_body(expires_in: int = 28800) -> dict:
    """Build a successful OAuth refresh response body (OAuth 2.0 shape)."""
    return {
        "access_token": "sk-ant-oat01-NEW_ACCESS",
        "refresh_token": "sk-ant-ort01-NEW_REFRESH",
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "user:inference user:profile user:mcp_servers",
    }


def _mock_httpx_client(response: httpx.Response) -> tuple[MagicMock, AsyncMock]:
    """Build a (factory, fake_client) pair for injecting into ClaudeCodeOAuth.

    The factory, when called, returns an async context manager that yields
    a fake AsyncClient whose ``.post()`` returns *response*. Returns both
    so tests can assert on the fake_client's call args.
    """
    fake_client = AsyncMock()
    fake_client.post.return_value = response

    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_client)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm
    return factory, fake_client


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------


class TestConstants:
    """Sanity-check the constants match the values the SF-77 spike validated."""

    def test_keychain_service_name(self):
        assert KEYCHAIN_SERVICE == "Claude Code-credentials"

    def test_refresh_url(self):
        assert OAUTH_REFRESH_URL == "https://platform.claude.com/v1/oauth/token"

    def test_client_id(self):
        assert OAUTH_CLIENT_ID == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

    def test_anthropic_version(self):
        assert ANTHROPIC_VERSION == "2023-06-01"

    def test_anthropic_beta_header_present(self):
        # Must include oauth beta for scope check + claude-code beta
        # for CLI rate limit pool access.
        assert "oauth-2025-04-20" in ANTHROPIC_BETA
        assert "claude-code-20250219" in ANTHROPIC_BETA

    def test_refresh_window(self):
        assert REFRESH_WINDOW_SECONDS == 60


class TestReadFromStore:
    @pytest.mark.anyio
    async def test_first_call_reads_credential_store(self):
        creds = _fresh_creds()
        store = FakeCredentialStore({(KEYCHAIN_SERVICE, "me"): _keychain_value(creds)})
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        headers = await auth.get_authorization_header()

        assert store.read_calls == [(KEYCHAIN_SERVICE, "me")]
        assert headers["Authorization"] == "Bearer sk-ant-oat01-CURRENT_ACCESS"
        assert headers["anthropic-version"] == ANTHROPIC_VERSION
        assert headers["anthropic-beta"] == ANTHROPIC_BETA

    @pytest.mark.anyio
    async def test_second_call_uses_cache(self):
        creds = _fresh_creds()
        store = FakeCredentialStore({(KEYCHAIN_SERVICE, "me"): _keychain_value(creds)})
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        await auth.get_authorization_header()
        await auth.get_authorization_header()

        # Only one read — second call hit the cache
        assert len(store.read_calls) == 1

    @pytest.mark.anyio
    async def test_missing_credential_raises_credential_not_found_error(self):
        store = FakeCredentialStore({})  # no entry
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        with pytest.raises(CredentialNotFoundError, match="claude auth login"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_invalid_json_raises_auth_error(self):
        store = FakeCredentialStore({(KEYCHAIN_SERVICE, "me"): "not json"})
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        with pytest.raises(AuthError, match="not valid JSON"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_missing_claudeAiOauth_key_raises_auth_error(self):
        store = FakeCredentialStore({(KEYCHAIN_SERVICE, "me"): json.dumps({"wrongKey": {}})})
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        with pytest.raises(AuthError, match="claudeAiOauth"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_missing_required_fields_raises_auth_error(self):
        partial = {"accessToken": "x"}  # missing refreshToken + expiresAt
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): json.dumps({"claudeAiOauth": partial})}
        )
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        with pytest.raises(AuthError, match="missing required keys"):
            await auth.get_authorization_header()


class TestExpiryDetection:
    def _make(self, seconds_from_now: float) -> ClaudeCodeOAuth:
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now))}
        )
        return ClaudeCodeOAuth(credential_store=store, account="me")

    def test_fresh_token_not_expired(self):
        auth = self._make(seconds_from_now=3600)
        creds = _fresh_creds(3600)
        assert auth._is_expired(creds) is False

    def test_token_outside_refresh_window_not_expired(self):
        auth = self._make(seconds_from_now=120)
        creds = _fresh_creds(120)
        assert auth._is_expired(creds) is False

    def test_token_inside_refresh_window_expired(self):
        auth = self._make(seconds_from_now=30)
        creds = _fresh_creds(30)
        # 30s remaining is less than 60s refresh window → counted as expired
        assert auth._is_expired(creds) is True

    def test_already_expired_token_expired(self):
        auth = self._make(seconds_from_now=-100)
        creds = _fresh_creds(-100)
        assert auth._is_expired(creds) is True


class TestRefresh:
    @pytest.mark.anyio
    async def test_expired_token_triggers_refresh(self):
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, fake_client = _mock_httpx_client(refresh_resp)
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        headers = await auth.get_authorization_header()

        # Refresh called
        fake_client.post.assert_called_once()
        args, kwargs = fake_client.post.call_args
        assert args[0] == OAUTH_REFRESH_URL
        assert kwargs["json"]["grant_type"] == "refresh_token"
        assert kwargs["json"]["client_id"] == OAUTH_CLIENT_ID
        assert kwargs["json"]["refresh_token"] == "sk-ant-ort01-CURRENT_REFRESH"
        assert kwargs["json"]["scope"] == " ".join(OAUTH_REFRESH_SCOPES)

        # Headers use the new token
        assert headers["Authorization"] == "Bearer sk-ant-oat01-NEW_ACCESS"

    @pytest.mark.anyio
    async def test_refresh_writes_back_to_credential_store(self):
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, _ = _mock_httpx_client(refresh_resp)
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        await auth.get_authorization_header()

        # Store was written with the new token
        assert len(store.write_calls) == 1
        _svc, _acct, value = store.write_calls[0]
        parsed = json.loads(value)
        assert parsed["claudeAiOauth"]["accessToken"] == "sk-ant-oat01-NEW_ACCESS"
        assert parsed["claudeAiOauth"]["refreshToken"] == "sk-ant-ort01-NEW_REFRESH"

    @pytest.mark.anyio
    async def test_refresh_response_field_conversion(self):
        """expires_in (seconds) → expiresAt (ms), scope string → scopes list."""
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        refresh_resp = httpx.Response(200, json=_refresh_response_body(expires_in=7200))
        factory, _ = _mock_httpx_client(refresh_resp)
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        await auth.get_authorization_header()

        # Check what ended up in the store
        value = store.write_calls[0][2]
        parsed = json.loads(value)["claudeAiOauth"]

        # expires_in=7200 seconds → expiresAt in ms, roughly 7200_000 ms from now
        now_ms = time.time() * 1000
        assert parsed["expiresAt"] >= now_ms + 7100_000  # ≥ 7100s from now
        assert parsed["expiresAt"] <= now_ms + 7300_000  # ≤ 7300s from now

        # scope "user:inference user:profile user:mcp_servers" → list
        assert parsed["scopes"] == [
            "user:inference",
            "user:profile",
            "user:mcp_servers",
        ]

    @pytest.mark.anyio
    async def test_refresh_preserves_subscription_metadata(self):
        """subscriptionType / rateLimitTier are NOT in the refresh response
        and must be preserved from the old credential."""
        initial = _fresh_creds(seconds_from_now=-100)
        initial["subscriptionType"] = "max"
        initial["rateLimitTier"] = "default_claude_max_5x"
        store = FakeCredentialStore({(KEYCHAIN_SERVICE, "me"): _keychain_value(initial)})
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, _ = _mock_httpx_client(refresh_resp)
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        await auth.get_authorization_header()

        parsed = json.loads(store.write_calls[0][2])["claudeAiOauth"]
        assert parsed["subscriptionType"] == "max"
        assert parsed["rateLimitTier"] == "default_claude_max_5x"

    @pytest.mark.anyio
    async def test_refresh_401_raises_auth_error(self):
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        factory, _ = _mock_httpx_client(httpx.Response(401, json={"error": "invalid_grant"}))
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        with pytest.raises(AuthError, match="claude auth login"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_refresh_5xx_raises_auth_error(self):
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        factory, _ = _mock_httpx_client(httpx.Response(500, text="internal server error"))
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        with pytest.raises(AuthError, match="500"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_refresh_network_error_raises_auth_error(self):
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.side_effect = httpx.ConnectError("no network")
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        with pytest.raises(AuthError, match="unreachable"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_refresh_response_missing_access_token_raises(self):
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        bad_body = {"refresh_token": "x", "expires_in": 3600}  # missing access_token
        factory, _ = _mock_httpx_client(httpx.Response(200, json=bad_body))
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        with pytest.raises(AuthError, match="access_token"):
            await auth.get_authorization_header()


class TestConcurrency:
    @pytest.mark.anyio
    async def test_concurrent_calls_serialize_refresh(self):
        """Two coroutines hit expired token at once; only one refresh fires;
        both see the new token."""
        store = FakeCredentialStore(
            {(KEYCHAIN_SERVICE, "me"): _keychain_value(_fresh_creds(seconds_from_now=-100))}
        )
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, fake_client = _mock_httpx_client(refresh_resp)
        auth = ClaudeCodeOAuth(credential_store=store, account="me", http_client_factory=factory)

        # Fire two concurrent get_authorization_header calls
        headers_a, headers_b = await asyncio.gather(
            auth.get_authorization_header(),
            auth.get_authorization_header(),
        )

        # Only one refresh call actually went through
        assert fake_client.post.call_count == 1

        # Both callers got the new token
        assert headers_a["Authorization"] == "Bearer sk-ant-oat01-NEW_ACCESS"
        assert headers_b["Authorization"] == "Bearer sk-ant-oat01-NEW_ACCESS"


class TestInvalidateCache:
    @pytest.mark.anyio
    async def test_invalidate_forces_re_read(self):
        creds = _fresh_creds(seconds_from_now=3600)
        store = FakeCredentialStore({(KEYCHAIN_SERVICE, "me"): _keychain_value(creds)})
        auth = ClaudeCodeOAuth(credential_store=store, account="me")

        await auth.get_authorization_header()
        assert len(store.read_calls) == 1

        auth.invalidate_cache()
        await auth.get_authorization_header()

        # Cache invalidation forced another read
        assert len(store.read_calls) == 2
