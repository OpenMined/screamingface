"""Probe for the Claude Code OAuth credential in the macOS keychain.

Used by the e2e suite to gate live-Anthropic tests. We deliberately do NOT
read the token here — only check that the keychain entry exists. Reading
the token is reserved for production code paths that need to call Anthropic
directly (currently the aigateway) and for the test-only helper
`claude_oauth_token.py` which emulates a Claude Code client.
"""

from __future__ import annotations

import os
import shutil
import subprocess

_KEYCHAIN_SERVICE = "Claude Code-credentials"
_TIMEOUT_SECONDS = 3


def has_claude_code_oauth() -> bool:
    """Return True iff the Claude Code OAuth keychain entry exists for $USER."""
    if not shutil.which("security"):
        return False
    user = os.environ.get("USER", "")
    if not user:
        return False
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
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
