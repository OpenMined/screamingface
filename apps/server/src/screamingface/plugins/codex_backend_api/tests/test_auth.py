"""Unit tests for codex-backend-api CodexOAuth.

All tests mock file I/O and the httpx client so they run in milliseconds
and are fully hermetic.
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.codex_backend_api.auth import (
    AUTH_FILE_PATH,
    OAUTH_CLIENT_ID,
    OAUTH_TOKEN_URL,
    REFRESH_WINDOW_SECONDS,
    CodexOAuth,
    _decode_jwt_exp,
)
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _make_jwt(exp: float) -> str:
    """Build a minimal JWT with the given exp claim (no real signature)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fake-signature").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


def _make_auth_json(*, exp_offset: float = 3600) -> dict:
    """Build a valid auth.json structure with an access token expiring at now + offset."""
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": _make_jwt(time.time() + exp_offset),
            "refresh_token": "rt_test_refresh",
            "id_token": "id_test",
            "account_id": "acct_test",
        },
        "last_refresh": "2026-01-01T00:00:00Z",
    }


def _write_auth(tmp_path, data: dict):
    """Write auth data to a temp auth.json."""
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps(data))
    return auth_file


def _mock_factory(response: httpx.Response):
    """Build a fake httpx client factory."""
    fake_client = AsyncMock()
    fake_client.post.return_value = response
    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_client)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm
    return factory, fake_client


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------


class TestConstants:
    def test_auth_file_path_default(self):
        from pathlib import Path

        assert AUTH_FILE_PATH == Path.home() / ".codex" / "auth.json"

    def test_refresh_url(self):
        assert OAUTH_TOKEN_URL == "https://auth.openai.com/oauth/token"

    def test_client_id(self):
        assert OAUTH_CLIENT_ID == "app_EMoamEEZ73f0CkXaXp7hrann"

    def test_refresh_window(self):
        assert REFRESH_WINDOW_SECONDS == 60


# ----------------------------------------------------------------------------
# JWT decode
# ----------------------------------------------------------------------------


class TestJwtDecode:
    def test_valid_jwt(self):
        exp = time.time() + 3600
        token = _make_jwt(exp)
        assert _decode_jwt_exp(token) == exp

    def test_invalid_jwt_no_dots(self):
        assert _decode_jwt_exp("not-a-jwt") is None

    def test_invalid_jwt_bad_base64(self):
        assert _decode_jwt_exp("a.!!!.b") is None

    def test_jwt_missing_exp(self):
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=")
        payload = base64.urlsafe_b64encode(b'{"sub":"user"}').rstrip(b"=")
        token = f"{header.decode()}.{payload.decode()}.sig"
        assert _decode_jwt_exp(token) is None


# ----------------------------------------------------------------------------
# Read from file
# ----------------------------------------------------------------------------


class TestReadFromFile:
    def test_missing_file_raises_credential_not_found(self, tmp_path):
        auth = CodexOAuth(auth_file=tmp_path / "missing.json")
        with pytest.raises(CredentialNotFoundError, match="codex auth login"):
            auth._read_from_file()

    def test_invalid_json_raises_auth_error(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text("not json!")
        auth = CodexOAuth(auth_file=auth_file)
        with pytest.raises(AuthError, match="not valid JSON"):
            auth._read_from_file()

    def test_missing_tokens_key_raises_auth_error(self, tmp_path):
        auth_file = _write_auth(tmp_path, {"OPENAI_API_KEY": "test"})
        auth = CodexOAuth(auth_file=auth_file)
        with pytest.raises(AuthError, match="missing the 'tokens' key"):
            auth._read_from_file()

    def test_missing_access_token_raises_auth_error(self, tmp_path):
        auth_file = _write_auth(tmp_path, {"tokens": {"refresh_token": "rt"}})
        auth = CodexOAuth(auth_file=auth_file)
        with pytest.raises(AuthError, match="missing required keys"):
            auth._read_from_file()

    def test_valid_file_returns_tokens(self, tmp_path):
        data = _make_auth_json()
        auth_file = _write_auth(tmp_path, data)
        auth = CodexOAuth(auth_file=auth_file)
        tokens = auth._read_from_file()
        assert tokens["access_token"] == data["tokens"]["access_token"]
        assert tokens["refresh_token"] == "rt_test_refresh"


# ----------------------------------------------------------------------------
# Expiry
# ----------------------------------------------------------------------------


class TestExpiry:
    def test_not_expired(self, tmp_path):
        data = _make_auth_json(exp_offset=3600)
        auth = CodexOAuth(auth_file=tmp_path / "auth.json")
        assert not auth._is_expired(data["tokens"])

    def test_within_refresh_window(self, tmp_path):
        data = _make_auth_json(exp_offset=30)  # 30s < REFRESH_WINDOW_SECONDS
        auth = CodexOAuth(auth_file=tmp_path / "auth.json")
        assert auth._is_expired(data["tokens"])

    def test_already_expired(self, tmp_path):
        data = _make_auth_json(exp_offset=-100)
        auth = CodexOAuth(auth_file=tmp_path / "auth.json")
        assert auth._is_expired(data["tokens"])


# ----------------------------------------------------------------------------
# get_authorization_header
# ----------------------------------------------------------------------------


def _token_exchange_response(exp_offset: float = 3600) -> httpx.Response:
    """Build a mock token exchange success response."""
    api_token = _make_jwt(time.time() + exp_offset)
    return httpx.Response(
        200,
        json={
            "access_token": api_token,
            "token_type": "Bearer",
            "expires_in": int(exp_offset),
        },
    )


class TestGetAuthorizationHeader:
    @pytest.mark.anyio
    async def test_returns_bearer_header(self, tmp_path):
        data = _make_auth_json()
        auth_file = _write_auth(tmp_path, data)
        factory, _ = _mock_factory(_token_exchange_response())
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        headers = await auth.get_authorization_header()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        # No anthropic-specific headers
        assert "anthropic-version" not in headers

    @pytest.mark.anyio
    async def test_cache_hit(self, tmp_path):
        data = _make_auth_json()
        auth_file = _write_auth(tmp_path, data)
        factory, _ = _mock_factory(_token_exchange_response())
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        h1 = await auth.get_authorization_header()
        h2 = await auth.get_authorization_header()
        assert h1 == h2

    @pytest.mark.anyio
    async def test_expired_triggers_refresh(self, tmp_path):
        data = _make_auth_json(exp_offset=10)  # about to expire
        auth_file = _write_auth(tmp_path, data)

        new_token = _make_jwt(time.time() + 7200)
        refresh_resp = httpx.Response(
            200,
            json={
                "access_token": new_token,
                "refresh_token": "rt_new",
                "expires_in": 7200,
            },
        )
        factory, _ = _mock_factory(refresh_resp)
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        headers = await auth.get_authorization_header()
        assert f"Bearer {new_token}" == headers["Authorization"]

    @pytest.mark.anyio
    async def test_invalidate_cache_forces_reread(self, tmp_path):
        data = _make_auth_json()
        auth_file = _write_auth(tmp_path, data)
        factory, _ = _mock_factory(_token_exchange_response())
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        await auth.get_authorization_header()
        auth.invalidate_cache()
        assert auth._cached is None
        assert auth._api_token is None


# ----------------------------------------------------------------------------
# Refresh
# ----------------------------------------------------------------------------


class TestRefresh:
    @pytest.mark.anyio
    async def test_refresh_posts_correct_body(self, tmp_path):
        data = _make_auth_json(exp_offset=10)
        auth_file = _write_auth(tmp_path, data)

        new_token = _make_jwt(time.time() + 7200)
        refresh_resp = httpx.Response(
            200,
            json={
                "access_token": new_token,
                "refresh_token": "rt_refreshed",
                "expires_in": 7200,
            },
        )
        factory, fake_client = _mock_factory(refresh_resp)
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        await auth.refresh()

        call_kwargs = fake_client.post.call_args
        assert call_kwargs.args[0] == OAUTH_TOKEN_URL
        body = call_kwargs.kwargs["json"]
        assert body["grant_type"] == "refresh_token"
        assert body["client_id"] == OAUTH_CLIENT_ID
        assert body["refresh_token"] == "rt_test_refresh"

    @pytest.mark.anyio
    async def test_refresh_writes_back_to_file(self, tmp_path):
        data = _make_auth_json(exp_offset=10)
        auth_file = _write_auth(tmp_path, data)

        new_token = _make_jwt(time.time() + 7200)
        refresh_resp = httpx.Response(
            200,
            json={
                "access_token": new_token,
                "refresh_token": "rt_new",
                "expires_in": 7200,
            },
        )
        factory, _ = _mock_factory(refresh_resp)
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        await auth.refresh()

        written = json.loads(auth_file.read_text())
        assert written["tokens"]["access_token"] == new_token
        assert written["tokens"]["refresh_token"] == "rt_new"
        assert "last_refresh" in written

    @pytest.mark.anyio
    async def test_refresh_401_raises_auth_error(self, tmp_path):
        data = _make_auth_json(exp_offset=10)
        auth_file = _write_auth(tmp_path, data)

        factory, _ = _mock_factory(httpx.Response(401, text="Unauthorized"))
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        with pytest.raises(AuthError, match="could not be refreshed"):
            await auth.refresh()

    @pytest.mark.anyio
    async def test_refresh_500_raises_auth_error(self, tmp_path):
        data = _make_auth_json(exp_offset=10)
        auth_file = _write_auth(tmp_path, data)

        factory, _ = _mock_factory(httpx.Response(500, text="Internal error"))
        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        with pytest.raises(AuthError, match="refresh failed with status 500"):
            await auth.refresh()

    @pytest.mark.anyio
    async def test_refresh_network_error_raises_auth_error(self, tmp_path):
        data = _make_auth_json(exp_offset=10)
        auth_file = _write_auth(tmp_path, data)

        factory = MagicMock()
        cm = MagicMock()
        fake_client = AsyncMock()
        fake_client.post.side_effect = httpx.ConnectError("Connection refused")
        cm.__aenter__ = AsyncMock(return_value=fake_client)
        cm.__aexit__ = AsyncMock(return_value=None)
        factory.return_value = cm

        auth = CodexOAuth(auth_file=auth_file, http_client_factory=factory)
        with pytest.raises(AuthError, match="unreachable"):
            await auth.refresh()


@pytest.mark.asyncio
async def test_codex_oauth_uses_aigw_source_when_set():
    from unittest.mock import AsyncMock

    from screamingface.plugins.codex_backend_api.auth import CodexOAuth
    from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource

    fake = AsyncMock(spec=AigwTokenSource)
    fake.fetch_token.return_value = "aigw-codex-token"

    strat = CodexOAuth(aigw_source=fake)
    headers = await strat.get_authorization_header()

    assert headers == {"Authorization": "Bearer aigw-codex-token"}
    fake.fetch_token.assert_awaited_once()
