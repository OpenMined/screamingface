"""macOS system-keychain trust management for the mitmproxy CA cert.

mitmproxy generates a self-signed CA cert and uses it to MITM TLS
connections. The OS won't trust intercepted connections unless this
CA is in the system keychain. Adding it requires a one-time
admin-credential prompt (idempotent on re-run).

Pulled out of ``plugin.py`` during SF-134.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

from screamingface.plugins.mitmproxy_intercept._sudo import sudo_run

logger = logging.getLogger(__name__)


def ensure_ca_trusted(ca_cert_path: str) -> None:
    """Trust the mitmproxy CA in the macOS system keychain (idempotent)."""
    if platform.system() != "Darwin":
        return

    ca_cert = Path(ca_cert_path).expanduser()
    if not ca_cert.exists():
        return

    # Check if already trusted by looking for the cert in the system keychain
    result = subprocess.run(
        ["security", "find-certificate", "-c", "mitmproxy", "/Library/Keychains/System.keychain"],
        capture_output=True,
    )
    if result.returncode == 0:
        logger.debug("Mitmproxy CA already trusted in system keychain")
        return

    logger.info("Trusting mitmproxy CA in system keychain...")
    sudo_run(
        [
            "security",
            "add-trusted-cert",
            "-d",
            "-p",
            "ssl",
            "-p",
            "basic",
            "-k",
            "/Library/Keychains/System.keychain",
            str(ca_cert),
        ]
    )
    logger.info("Mitmproxy CA trusted")
