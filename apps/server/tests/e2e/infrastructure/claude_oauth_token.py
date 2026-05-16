"""Read the Claude Code OAuth access token from the macOS keychain.

Test-infrastructure ONLY. Production code (the claude-frontend proxy) is
deliberately a transparent auth pass-through and must not consume this
helper — clients (Claude Code) attach their own auth. This helper exists
solely so e2e tests can emulate a Claude Code client that sends a real
Authorization: Bearer header to the proxy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

_KEYCHAIN_SERVICE = "Claude Code-credentials"
_TIMEOUT_SECONDS = 3


class OAuthMissingError(RuntimeError):
    """Keychain entry not present, or the security CLI is unavailable."""


class OAuthExpiredError(RuntimeError):
    """Keychain entry is present but the access token's expiresAt has passed."""


class OAuthMalformedError(RuntimeError):
    """Keychain blob isn't the expected Claude Code shape."""


def read_claude_code_oauth_access_token() -> str:
    """Return the current OAuth access token from the macOS keychain.

    Raises:
        OAuthMissingError: keychain entry absent, security CLI missing,
            or $USER not set.
        OAuthExpiredError: blob present but expiresAt is in the past.
        OAuthMalformedError: blob is not valid JSON or missing required
            fields.
    """
    if not shutil.which("security"):
        raise OAuthMissingError("macOS `security` CLI not on PATH")
    user = os.environ.get("USER", "")
    if not user:
        raise OAuthMissingError("$USER not set; cannot read keychain")
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                user,
                "-w",
            ],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OAuthMissingError(f"keychain probe failed: {exc}") from exc
    if result.returncode != 0:
        raise OAuthMissingError(f"No keychain entry for {_KEYCHAIN_SERVICE!r}; run `claude /login`")

    try:
        outer = json.loads(result.stdout)
        creds = outer["claudeAiOauth"]
        access_token = creds["accessToken"]
        expires_at_ms = int(creds["expiresAt"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise OAuthMalformedError(f"Claude Code keychain blob has unexpected shape: {exc}") from exc

    if time.time() * 1000 >= expires_at_ms:
        raise OAuthExpiredError("OAuth access token has expired; run `claude /login` to refresh")
    return access_token
