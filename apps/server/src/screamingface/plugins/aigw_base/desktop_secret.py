"""Desktop-to-SF shared-secret validation."""

from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import HTTPException, Request

DESKTOP_SECRET_HEADER = "X-SF-Desktop-Secret"
_ENV_SECRET = "SF_DESKTOP_SECRET"
_ENV_SECRET_FILE = "SF_DESKTOP_SECRET_FILE"


def configured_desktop_secret() -> str | None:
    direct = os.getenv(_ENV_SECRET)
    if direct:
        return direct.strip()
    path = os.getenv(_ENV_SECRET_FILE)
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def require_desktop_secret(request: Request) -> None:
    expected = configured_desktop_secret()
    if expected is None:
        return
    supplied = request.headers.get(DESKTOP_SECRET_HEADER)
    if supplied and hmac.compare_digest(supplied, expected):
        return
    raise HTTPException(
        status_code=401,
        detail={"code": "desktop_secret_required", "message": "Desktop secret is required"},
    )
