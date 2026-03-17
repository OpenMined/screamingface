"""SSL certificate management with mkcert."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CERT_DIR = Path("~/.screamingface/certs").expanduser()
CERT_FILE = DEFAULT_CERT_DIR / "localhost+1.pem"
KEY_FILE = DEFAULT_CERT_DIR / "localhost+1-key.pem"


def ensure_ssl() -> tuple[Path, Path]:
    """Ensure mkcert is installed and certs exist. Auto-generate if needed."""
    if CERT_FILE.exists() and KEY_FILE.exists():
        logger.info("SSL certs found at %s", DEFAULT_CERT_DIR)
        return CERT_FILE, KEY_FILE
    ensure_mkcert_installed()
    ensure_ca_installed()
    generate_certs()
    return CERT_FILE, KEY_FILE


def ensure_mkcert_installed() -> None:
    """Check that mkcert is available, install via brew if missing."""
    if shutil.which("mkcert"):
        return
    if not shutil.which("brew"):
        raise RuntimeError(
            "mkcert is not installed and Homebrew is not available. "
            "Install mkcert manually: https://github.com/FiloSottile/mkcert"
        )
    logger.info("Installing mkcert via Homebrew...")
    subprocess.run(["brew", "install", "mkcert"], check=True)


def ensure_ca_installed() -> None:
    """Run mkcert -install to ensure the local CA is trusted (idempotent)."""
    logger.info("Ensuring mkcert CA is installed...")
    subprocess.run(["mkcert", "-install"], check=True)


def generate_certs() -> None:
    """Generate localhost certs using mkcert."""
    DEFAULT_CERT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Generating SSL certs in %s", DEFAULT_CERT_DIR)
    subprocess.run(
        [
            "mkcert",
            "-cert-file",
            str(CERT_FILE),
            "-key-file",
            str(KEY_FILE),
            "localhost",
            "127.0.0.1",
        ],
        check=True,
    )
