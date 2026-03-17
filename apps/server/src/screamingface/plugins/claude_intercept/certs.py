"""SSL certificate generation for intercepted domains."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from screamingface.core.ssl import DEFAULT_CERT_DIR, ensure_ca_installed, ensure_mkcert_installed

logger = logging.getLogger(__name__)

INTERCEPT_CERT = DEFAULT_CERT_DIR / "claude-intercept.pem"
INTERCEPT_KEY = DEFAULT_CERT_DIR / "claude-intercept-key.pem"


def ensure_intercept_certs(domains: list[str]) -> tuple[Path, Path]:
    """Generate SSL certs covering localhost + intercepted domains.

    Always regenerates to ensure domain list is current.
    Returns (cert_path, key_path).
    """
    ensure_mkcert_installed()
    ensure_ca_installed()

    DEFAULT_CERT_DIR.mkdir(parents=True, exist_ok=True)

    san_names = ["localhost", "127.0.0.1", *domains]
    logger.info("Generating intercept certs for %s", san_names)

    subprocess.run(
        [
            "mkcert",
            "-cert-file",
            str(INTERCEPT_CERT),
            "-key-file",
            str(INTERCEPT_KEY),
            *san_names,
        ],
        check=True,
    )

    return INTERCEPT_CERT, INTERCEPT_KEY
