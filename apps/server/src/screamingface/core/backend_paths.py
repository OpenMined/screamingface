"""Shared helpers for URL4 backend-call paths and profile aliases."""

from __future__ import annotations

import re

PROFILE_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def is_valid_profile_alias(alias: str) -> bool:
    return PROFILE_ALIAS_RE.match(alias) is not None


def normalize_backend_call_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    normalized = path.rstrip("/")
    if not normalized or not normalized.startswith("/"):
        return None
    return normalized
