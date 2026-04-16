"""Unit tests for gemini-backend-api GeminiAuth.

All tests mock the credential file and httpx client so they run
in milliseconds and are fully hermetic. No real file reads, no
real network calls.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.gemini_backend_api.auth import (
    CLI_VERSION,
    GOOGLE_TOKEN_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_CREDS_PATH,
    REFRESH_WINDOW_SECONDS,
    GeminiAuth,
)
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError

# ----------------------------------------------------------------------------
# Fixtures and helpers
# ----------------------------------------------------------------------------


def _fresh_creds(seconds_from_now: float = 3600) -> dict:
    """Build a valid credential dict with a chosen expiry offset."""
    return {
        "access_token": "ya29.CURRENT_ACCESS",
        "refresh_token": "1//CURRENT_REFRESH",
        "id_token": "eyJ.test.jwt",
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "expiry_date": int((time.time() + seconds_from_now) * 1000),
    }


def _write_creds(tmp_path: Path, creds: dict) -> Path:
    """Write credentials to a temp file and return the path."""
    creds_file = tmp_path / "oauth_creds.json"
    creds_file.write_text(json.dumps(creds))
    return creds_file


def _refresh_response_body(expires_in: int = 3600) -> dict:
    """Build a successful Google OAuth refresh response body."""
    return {
        "access_token": "ya29.NEW_ACCESS",
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "id_token": "eyJ.new.jwt",
    }


def _mock_httpx_client(response: httpx.Response) -> tuple[MagicMock, AsyncMock]:
    """Build a (factory, fake_client) pair for injecting into GeminiAuth."""
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
    """Sanity-check the constants match the Gemini CLI values."""

    def test_creds_path_default(self):
        assert OAUTH_CREDS_PATH.name == "oauth_creds.json"
        assert OAUTH_CREDS_PATH.parent.name == ".gemini"

    def test_token_url(self):
        assert GOOGLE_TOKEN_URL == "https://oauth2.googleapis.com/token"

    def test_client_id(self):
        assert OAUTH_CLIENT_ID == "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"

    def test_client_secret(self):
        assert OAUTH_CLIENT_SECRET == "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"

    def test_refresh_window(self):
        assert REFRESH_WINDOW_SECONDS == 60

    def test_cli_version(self):
        assert CLI_VERSION == "0.37.1"


class TestApiKeyAuth:
    def test_is_api_key_auth_false_by_default(self):
        auth = GeminiAuth()
        assert auth.is_api_key_auth() is False

    def test_is_api_key_auth_true_with_google_api_key(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        auth = GeminiAuth()
        assert auth.is_api_key_auth() is True

    def test_is_api_key_auth_true_with_gemini_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        auth = GeminiAuth()
        assert auth.is_api_key_auth() is True

    @pytest.mark.anyio
    async def test_api_key_header_google_api_key(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "my-google-key")
        auth = GeminiAuth()
        headers = await auth.get_authorization_header()
        assert headers == {"x-goog-api-key": "my-google-key"}

    @pytest.mark.anyio
    async def test_api_key_header_gemini_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "my-gemini-key")
        auth = GeminiAuth()
        headers = await auth.get_authorization_header()
        assert headers == {"x-goog-api-key": "my-gemini-key"}


class TestReadFromFile:
    @pytest.mark.anyio
    async def test_first_call_reads_credential_file(self, tmp_path):
        creds = _fresh_creds()
        creds_file = _write_creds(tmp_path, creds)
        auth = GeminiAuth(creds_file=creds_file)

        headers = await auth.get_authorization_header()

        assert headers["Authorization"] == "Bearer ya29.CURRENT_ACCESS"
        assert "User-Agent" in headers
        assert "GeminiCLI" in headers["User-Agent"]

    @pytest.mark.anyio
    async def test_second_call_uses_cache(self, tmp_path):
        creds = _fresh_creds()
        creds_file = _write_creds(tmp_path, creds)
        auth = GeminiAuth(creds_file=creds_file)

        await auth.get_authorization_header()
        # Modify file to detect if it's re-read
        creds_file.write_text(json.dumps({**creds, "access_token": "ya29.CHANGED"}))
        headers = await auth.get_authorization_header()

        # Should still have the cached token
        assert headers["Authorization"] == "Bearer ya29.CURRENT_ACCESS"

    @pytest.mark.anyio
    async def test_missing_file_raises_credential_not_found(self, tmp_path):
        auth = GeminiAuth(creds_file=tmp_path / "nonexistent.json")

        with pytest.raises(CredentialNotFoundError, match="gemini"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_invalid_json_raises_auth_error(self, tmp_path):
        creds_file = tmp_path / "oauth_creds.json"
        creds_file.write_text("not json")
        auth = GeminiAuth(creds_file=creds_file)

        with pytest.raises(AuthError, match="not valid JSON"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_non_dict_raises_auth_error(self, tmp_path):
        creds_file = tmp_path / "oauth_creds.json"
        creds_file.write_text('"just a string"')
        auth = GeminiAuth(creds_file=creds_file)

        with pytest.raises(AuthError, match="not a JSON object"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_missing_required_fields_raises_auth_error(self, tmp_path):
        creds_file = _write_creds(tmp_path, {"access_token": "x"})  # missing refresh_token
        auth = GeminiAuth(creds_file=creds_file)

        with pytest.raises(AuthError, match="missing required keys"):
            await auth.get_authorization_header()


class TestExpiryDetection:
    def _make(self, tmp_path: Path, seconds_from_now: float) -> GeminiAuth:
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now))
        return GeminiAuth(creds_file=creds_file)

    def test_fresh_token_not_expired(self, tmp_path):
        auth = self._make(tmp_path, seconds_from_now=3600)
        creds = _fresh_creds(3600)
        assert auth._is_expired(creds) is False

    def test_token_outside_refresh_window_not_expired(self, tmp_path):
        auth = self._make(tmp_path, seconds_from_now=120)
        creds = _fresh_creds(120)
        assert auth._is_expired(creds) is False

    def test_token_inside_refresh_window_expired(self, tmp_path):
        auth = self._make(tmp_path, seconds_from_now=30)
        creds = _fresh_creds(30)
        # 30s remaining < 60s refresh window → expired
        assert auth._is_expired(creds) is True

    def test_already_expired_token_expired(self, tmp_path):
        auth = self._make(tmp_path, seconds_from_now=-100)
        creds = _fresh_creds(-100)
        assert auth._is_expired(creds) is True


class TestRefresh:
    @pytest.mark.anyio
    async def test_expired_token_triggers_refresh(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, fake_client = _mock_httpx_client(refresh_resp)
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        headers = await auth.get_authorization_header()

        # Refresh called
        fake_client.post.assert_called_once()
        args, kwargs = fake_client.post.call_args
        assert args[0] == GOOGLE_TOKEN_URL
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["client_id"] == OAUTH_CLIENT_ID
        assert kwargs["data"]["client_secret"] == OAUTH_CLIENT_SECRET
        assert kwargs["data"]["refresh_token"] == "1//CURRENT_REFRESH"

        # Headers use the new token
        assert headers["Authorization"] == "Bearer ya29.NEW_ACCESS"

    @pytest.mark.anyio
    async def test_refresh_writes_back_to_file(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, _ = _mock_httpx_client(refresh_resp)
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        await auth.get_authorization_header()

        # File was updated with new token
        updated = json.loads(creds_file.read_text())
        assert updated["access_token"] == "ya29.NEW_ACCESS"
        assert updated["id_token"] == "eyJ.new.jwt"

    @pytest.mark.anyio
    async def test_refresh_preserves_refresh_token(self, tmp_path):
        """Google does NOT return a new refresh_token — old one must be kept."""
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        # Response without refresh_token (typical Google behavior)
        body = _refresh_response_body()
        refresh_resp = httpx.Response(200, json=body)
        factory, _ = _mock_httpx_client(refresh_resp)
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        await auth.get_authorization_header()

        updated = json.loads(creds_file.read_text())
        assert updated["refresh_token"] == "1//CURRENT_REFRESH"

    @pytest.mark.anyio
    async def test_refresh_expiry_calculation(self, tmp_path):
        """expires_in (seconds) → expiry_date (ms from epoch)."""
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        refresh_resp = httpx.Response(200, json=_refresh_response_body(expires_in=7200))
        factory, _ = _mock_httpx_client(refresh_resp)
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        await auth.get_authorization_header()

        updated = json.loads(creds_file.read_text())
        now_ms = time.time() * 1000
        assert updated["expiry_date"] >= now_ms + 7100_000  # ≥ 7100s from now
        assert updated["expiry_date"] <= now_ms + 7300_000  # ≤ 7300s from now

    @pytest.mark.anyio
    async def test_refresh_401_raises_auth_error(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        factory, _ = _mock_httpx_client(httpx.Response(401, json={"error": "invalid_grant"}))
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        with pytest.raises(AuthError, match="401"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_refresh_5xx_raises_auth_error(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        factory, _ = _mock_httpx_client(httpx.Response(500, text="internal server error"))
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        with pytest.raises(AuthError, match="500"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_refresh_network_error_raises_auth_error(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.side_effect = httpx.ConnectError("no network")
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        with pytest.raises(AuthError, match="unreachable"):
            await auth.get_authorization_header()

    @pytest.mark.anyio
    async def test_refresh_response_missing_access_token_raises(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        bad_body = {"expires_in": 3600}  # missing access_token
        factory, _ = _mock_httpx_client(httpx.Response(200, json=bad_body))
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        with pytest.raises(AuthError, match="access_token"):
            await auth.get_authorization_header()


class TestConcurrency:
    @pytest.mark.anyio
    async def test_concurrent_calls_serialize_refresh(self, tmp_path):
        """Two coroutines hit expired token at once; only one refresh fires."""
        creds_file = _write_creds(tmp_path, _fresh_creds(seconds_from_now=-100))
        refresh_resp = httpx.Response(200, json=_refresh_response_body())
        factory, fake_client = _mock_httpx_client(refresh_resp)
        auth = GeminiAuth(creds_file=creds_file, http_client_factory=factory)

        headers_a, headers_b = await asyncio.gather(
            auth.get_authorization_header(),
            auth.get_authorization_header(),
        )

        # Only one refresh call
        assert fake_client.post.call_count == 1
        # Both see the new token
        assert headers_a["Authorization"] == "Bearer ya29.NEW_ACCESS"
        assert headers_b["Authorization"] == "Bearer ya29.NEW_ACCESS"


class TestInvalidateCache:
    @pytest.mark.anyio
    async def test_invalidate_forces_re_read(self, tmp_path):
        creds = _fresh_creds(seconds_from_now=3600)
        creds_file = _write_creds(tmp_path, creds)
        auth = GeminiAuth(creds_file=creds_file)

        headers1 = await auth.get_authorization_header()
        assert headers1["Authorization"] == "Bearer ya29.CURRENT_ACCESS"

        # Update file and invalidate
        creds_file.write_text(json.dumps({**creds, "access_token": "ya29.UPDATED"}))
        auth.invalidate_cache()

        headers2 = await auth.get_authorization_header()
        assert headers2["Authorization"] == "Bearer ya29.UPDATED"


class TestUserAgentHeader:
    @pytest.mark.anyio
    async def test_oauth_headers_include_user_agent(self, tmp_path):
        creds_file = _write_creds(tmp_path, _fresh_creds())
        auth = GeminiAuth(creds_file=creds_file)

        headers = await auth.get_authorization_header()

        assert "User-Agent" in headers
        assert "GeminiCLI/" in headers["User-Agent"]
        assert "terminal" in headers["User-Agent"]

    @pytest.mark.anyio
    async def test_api_key_headers_no_user_agent(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        auth = GeminiAuth()

        headers = await auth.get_authorization_header()

        assert "User-Agent" not in headers
