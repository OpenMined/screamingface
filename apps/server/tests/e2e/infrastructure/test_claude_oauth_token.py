"""Unit tests for read_claude_code_oauth_access_token."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from tests.e2e.infrastructure.claude_oauth_token import (
    ClaudeOAuthError,
    OAuthExpiredError,
    OAuthMalformedError,
    OAuthMissingError,
    read_claude_code_oauth_access_token,
)

_FAR_FUTURE_MS = 9_999_999_999_999  # year 2286 — never expires within test runtime


def _completed(stdout: bytes, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def _keychain_blob(
    *, access: str = "oauth-access-abc", expires_at_ms: int = _FAR_FUTURE_MS
) -> bytes:
    return (
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": access,
                    "refreshToken": "ref-xyz",
                    "expiresAt": expires_at_ms,
                    "scopes": ["user:inference"],
                }
            }
        ).encode()
        + b"\n"
    )


def test_returns_access_token_on_happy_path(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with (
        patch("shutil.which", return_value="/usr/bin/security"),
        patch("subprocess.run", return_value=_completed(_keychain_blob(access="tkn-1"))),
    ):
        assert read_claude_code_oauth_access_token() == "tkn-1"


def test_raises_missing_when_security_missing(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value=None):
        with pytest.raises(OAuthMissingError):
            read_claude_code_oauth_access_token()


def test_raises_missing_when_user_unset(monkeypatch) -> None:
    monkeypatch.delenv("USER", raising=False)
    with patch("shutil.which", return_value="/usr/bin/security"):
        with pytest.raises(OAuthMissingError):
            read_claude_code_oauth_access_token()


def test_raises_missing_when_returncode_nonzero(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with (
        patch("shutil.which", return_value="/usr/bin/security"),
        patch("subprocess.run", return_value=_completed(b"", returncode=44)),
    ):
        with pytest.raises(OAuthMissingError):
            read_claude_code_oauth_access_token()


def test_raises_expired_when_token_past_expiry(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with (
        patch("shutil.which", return_value="/usr/bin/security"),
        patch("subprocess.run", return_value=_completed(_keychain_blob(expires_at_ms=1))),
    ):
        with pytest.raises(OAuthExpiredError):
            read_claude_code_oauth_access_token()


def test_raises_malformed_when_json_broken(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with (
        patch("shutil.which", return_value="/usr/bin/security"),
        patch("subprocess.run", return_value=_completed(b"{not-json")),
    ):
        with pytest.raises(OAuthMalformedError):
            read_claude_code_oauth_access_token()


def test_raises_malformed_when_field_missing(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    bad = json.dumps({"claudeAiOauth": {"refreshToken": "r", "expiresAt": _FAR_FUTURE_MS}}).encode()
    with (
        patch("shutil.which", return_value="/usr/bin/security"),
        patch("subprocess.run", return_value=_completed(bad)),
    ):
        with pytest.raises(OAuthMalformedError):
            read_claude_code_oauth_access_token()


def test_all_errors_share_base_class() -> None:
    """Callers should be able to catch any OAuth helper failure with one except."""
    assert issubclass(OAuthMissingError, ClaudeOAuthError)
    assert issubclass(OAuthExpiredError, ClaudeOAuthError)
    assert issubclass(OAuthMalformedError, ClaudeOAuthError)
