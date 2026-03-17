"""Make Node.js (and other runtimes) trust the mkcert CA.

macOS stores trusted CAs in the system Keychain, but Node.js ignores it —
it uses its own bundled CA bundle. The NODE_EXTRA_CA_CERTS env var tells
Node.js to trust additional CA certificates.

This module handles setup and teardown:
1. Adds NODE_EXTRA_CA_CERTS to all existing shell profiles
2. Sets it via launchctl for the current session (new processes only)
3. Removes both on teardown when the claude-intercept plugin is deactivated
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER = "# screamingface-node-ca"


def mkcert_ca_root() -> Path | None:
    """Return the path to mkcert's root CA certificate."""
    try:
        result = subprocess.run(
            ["mkcert", "-CAROOT"],
            capture_output=True,
            text=True,
            check=True,
        )
        ca_dir = Path(result.stdout.strip())
        ca_cert = ca_dir / "rootCA.pem"
        if ca_cert.exists():
            return ca_cert
        logger.warning("mkcert CA root not found at %s", ca_cert)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Could not determine mkcert CA root")
    return None


def ensure_node_trusts_ca() -> bool:
    """One-time setup: make Node.js trust the mkcert CA.

    Returns True if setup was performed or already in place.
    """
    ca_cert = mkcert_ca_root()
    if ca_cert is None:
        return False

    profile_ok = _ensure_shell_profile(ca_cert)
    _ensure_launchctl(ca_cert)

    return profile_ok


_RC_CANDIDATES = (
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".zprofile",
    ".profile",
)


def _shell_profiles() -> list[Path]:
    """Return all existing shell RC files that should be patched."""
    home = Path.home()
    profiles = [home / name for name in _RC_CANDIDATES if (home / name).exists()]
    if not profiles:
        profiles = [home / ".profile"]
    return profiles


def _ensure_shell_profile(ca_cert: Path) -> bool:
    """Add NODE_EXTRA_CA_CERTS to all shell profiles if not already present."""
    line = f'export NODE_EXTRA_CA_CERTS="{ca_cert}"  {MARKER}\n'
    any_written = False

    for profile in _shell_profiles():
        if profile.exists():
            content = profile.read_text()
            if MARKER in content:
                logger.debug("NODE_EXTRA_CA_CERTS already in %s", profile)
                any_written = True
                continue

        with profile.open("a") as f:
            f.write(f"\n{line}")
        logger.info("Added NODE_EXTRA_CA_CERTS to %s", profile)
        any_written = True

    return any_written


def remove_node_ca_trust() -> None:
    """Remove NODE_EXTRA_CA_CERTS from all shell profiles and launchctl."""
    _remove_shell_profile()
    _remove_launchctl()


def has_node_ca_trust() -> bool:
    """Check if the NODE_EXTRA_CA_CERTS marker exists in any shell profile."""
    return any(p.exists() and MARKER in p.read_text() for p in _shell_profiles())


def _remove_shell_profile() -> None:
    """Remove the NODE_EXTRA_CA_CERTS line from all shell profiles."""
    for profile in _shell_profiles():
        if not profile.exists():
            continue
        content = profile.read_text()
        if MARKER not in content:
            continue
        lines = content.splitlines(keepends=True)
        new_lines = [line for line in lines if MARKER not in line]
        profile.write_text("".join(new_lines))
        logger.info("Removed NODE_EXTRA_CA_CERTS from %s", profile)


def _remove_launchctl() -> None:
    """Unset NODE_EXTRA_CA_CERTS via launchctl."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["launchctl", "unsetenv", "NODE_EXTRA_CA_CERTS"],
            check=True,
            capture_output=True,
        )
        logger.info("Removed NODE_EXTRA_CA_CERTS via launchctl")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.debug("launchctl unsetenv failed (non-fatal)")


def _ensure_launchctl(ca_cert: Path) -> None:
    """Set NODE_EXTRA_CA_CERTS via launchctl for the current session.

    This makes it available to new processes spawned by launchd (e.g. apps
    launched from Spotlight/Dock). Only works on macOS.
    """
    if sys.platform != "darwin":
        return

    try:
        subprocess.run(
            ["launchctl", "setenv", "NODE_EXTRA_CA_CERTS", str(ca_cert)],
            check=True,
            capture_output=True,
        )
        logger.info("Set NODE_EXTRA_CA_CERTS via launchctl")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.debug("launchctl setenv failed (non-fatal)")
