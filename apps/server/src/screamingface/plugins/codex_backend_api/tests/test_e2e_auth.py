"""End-to-end test that validates real Codex CLI OAuth token access.

Reads ~/.codex/auth.json, validates structure, decodes the JWT, and
makes a lightweight API call to confirm the token is accepted by OpenAI.

Skipped automatically if:
- ~/.codex/auth.json doesn't exist (codex not installed / not logged in)
- CODEX_E2E environment variable is not set

Run with:
    CODEX_E2E=1 uv run pytest src/screamingface/plugins/codex_backend_api/tests/test_e2e_auth.py -v
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from screamingface.plugins.codex_backend_api.auth import (
    AUTH_FILE_PATH,
    _decode_jwt_exp,
)

_SKIP_REASON_NO_FILE = "~/.codex/auth.json not found — run 'codex auth login'"
_SKIP_REASON_NO_ENV = "Set CODEX_E2E=1 to run e2e auth tests"

pytestmark = [
    pytest.mark.skipif(not os.environ.get("CODEX_E2E"), reason=_SKIP_REASON_NO_ENV),
    pytest.mark.skipif(not AUTH_FILE_PATH.exists(), reason=_SKIP_REASON_NO_FILE),
]


class TestCodexAuthFileStructure:
    """Validate the auth.json file has the expected shape."""

    def test_file_is_valid_json(self):
        raw = AUTH_FILE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict)

    def test_has_tokens_key(self):
        data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
        assert "tokens" in data
        tokens = data["tokens"]
        assert isinstance(tokens, dict)

    def test_has_required_token_fields(self):
        data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
        tokens = data["tokens"]
        assert "access_token" in tokens, "Missing access_token"
        assert "refresh_token" in tokens, "Missing refresh_token"
        assert len(tokens["access_token"]) > 50, "access_token looks too short for a JWT"
        assert tokens["refresh_token"].startswith("rt_"), "refresh_token should start with rt_"


class TestCodexJwtDecode:
    """Validate the JWT access token can be decoded and has expected claims."""

    def test_jwt_has_three_parts(self):
        data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
        token = data["tokens"]["access_token"]
        parts = token.split(".")
        assert len(parts) == 3, f"JWT should have 3 parts, got {len(parts)}"

    def test_jwt_exp_is_decodable(self):
        data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
        token = data["tokens"]["access_token"]
        exp = _decode_jwt_exp(token)
        assert exp is not None, "Could not decode exp from JWT"
        assert isinstance(exp, float)

    def test_jwt_exp_is_in_future_or_refreshable(self):
        data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
        token = data["tokens"]["access_token"]
        exp = _decode_jwt_exp(token)
        assert exp is not None
        # Token might be expired (that's ok — refresh will fix it).
        # But it should have been valid at some point (not epoch 0).
        assert exp > 1700000000, f"exp {exp} looks invalid (before 2023)"


class TestCodexOAuthRefresh:
    """Test that the refresh token works and returns valid tokens.

    NOTE: The Codex CLI's OAuth tokens have ChatGPT scopes only
    (openid, profile, email, offline_access). Direct API calls require
    additional scope (api.responses.write) which the Codex CLI obtains
    internally via its built-in proxy. The token exchange grant type
    (RFC 8693) also appears to require internal Codex client privileges.

    For the SF plugin, auth.py reads the token from ~/.codex/auth.json,
    refreshes it to keep it valid, and builds Bearer headers. The actual
    API routing will either:
    (a) go through the Codex CLI proxy (when available), or
    (b) require the user to set OPENAI_API_KEY for direct API access.

    These tests validate the refresh flow works end-to-end.
    """

    @pytest.mark.anyio
    async def test_refresh_returns_fresh_tokens(self):
        """Refresh and verify we get a valid new access_token + id_token."""
        data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
        tokens = data["tokens"]

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                "https://auth.openai.com/oauth/token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                },
                headers={"content-type": "application/json"},
            )

        assert resp.status_code == 200, f"Refresh failed with {resp.status_code}: {resp.text[:200]}"
        fresh = resp.json()
        assert "access_token" in fresh
        assert "refresh_token" in fresh
        assert "id_token" in fresh
        assert "expires_in" in fresh

        # Verify the fresh access_token is a valid JWT
        at = fresh["access_token"]
        assert len(at.split(".")) == 3
        exp = _decode_jwt_exp(at)
        assert exp is not None
        assert exp > time.time(), "Fresh access_token should not be expired"

        # Verify the fresh id_token is also valid
        idt = fresh["id_token"]
        assert len(idt.split(".")) == 3
        id_exp = _decode_jwt_exp(idt)
        assert id_exp is not None
        assert id_exp > time.time(), "Fresh id_token should not be expired"
