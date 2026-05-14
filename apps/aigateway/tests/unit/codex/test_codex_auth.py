from __future__ import annotations

import json
import os
import time

import httpx
import pytest

from aigateway.core.errors import CredentialNotFoundError
from aigateway.plugins.codex_provider.auth import CodexOAuth, _atomic_write_auth_file
from aigateway.plugins.codex_provider.oauth_config import CODEX_OAUTH_TOKEN_URL

from .helpers import unsigned_jwt, write_codex_auth


def test_reads_file_backed_oauth_and_builds_chatgpt_headers(codex_home) -> None:
    auth_path = write_codex_auth(codex_home, account_id="acct-123")

    strategy = CodexOAuth(profile_name="default")
    creds = strategy._read_credential()
    headers = strategy._build_headers(creds)

    assert creds["kind"] == "oauth"
    assert creds["auth_file"] == str(auth_path)
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["ChatGPT-Account-Id"] == "acct-123"


def test_missing_codex_auth_file_raises_credential_not_found(codex_home) -> None:
    with pytest.raises(CredentialNotFoundError):
        CodexOAuth(profile_name="default")._read_credential()


@pytest.mark.asyncio
async def test_expired_oauth_refreshes_and_preserves_identity_fields(codex_home) -> None:
    old_id_token = unsigned_jwt({"sub": "sub-1", "name": "Codex User"})
    write_codex_auth(
        codex_home,
        access_exp=time.time() - 120,
        id_claims={"sub": "sub-1", "name": "Codex User"},
        account_id="acct-old",
    )
    new_access_token = unsigned_jwt({"exp": time.time() + 3600})
    requests: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"access_token": new_access_token, "refresh_token": "refresh-token-2"},
        )

    strategy = CodexOAuth(
        profile_name="default",
        http_client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(_handler), timeout=httpx.Timeout(5.0)
        ),
    )

    headers = await strategy.get_authorization_header()
    data = json.loads((codex_home / "auth.json").read_text())

    assert requests[0].url == CODEX_OAUTH_TOKEN_URL
    assert json.loads(requests[0].content)["scope"] == "openid profile email"
    assert headers["Authorization"] == f"Bearer {new_access_token}"
    assert headers["ChatGPT-Account-Id"] == "acct-old"
    assert data["tokens"]["access_token"] == new_access_token
    assert data["tokens"]["refresh_token"] == "refresh-token-2"
    assert data["tokens"]["account_id"] == "acct-old"
    assert data["tokens"]["id_token"] == old_id_token
    assert data["last_refresh"]


def test_extract_identity_from_unsigned_id_token() -> None:
    strategy = CodexOAuth(profile_name="default")
    identity = strategy.extract_identity(
        {"id_token": unsigned_jwt({"sub": "sub-1", "email": "user@example.com"})}
    )

    assert identity is not None
    assert identity.sub == "sub-1"
    assert identity.email == "user@example.com"


def test_atomic_write_preserves_stricter_permissions(tmp_path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"old": True}))
    path.chmod(0o400)

    _atomic_write_auth_file(path, {"new": True})

    assert json.loads(path.read_text()) == {"new": True}
    assert path.stat().st_mode & 0o777 == 0o400


def test_atomic_write_cleans_tmp_file_when_replace_fails(tmp_path, monkeypatch) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"old": True}))

    def _fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", _fail_replace)

    with pytest.raises(OSError):
        _atomic_write_auth_file(path, {"new": True})

    assert json.loads(path.read_text()) == {"old": True}
    assert not list(tmp_path.glob("*.tmp"))
