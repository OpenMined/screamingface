"""Shared RFC 9110 conditional-request helpers."""

from __future__ import annotations


def validator_matches(if_none_match: str | None, etag: str) -> bool:
    """Weakly compare an ``If-None-Match`` list with one unquoted entity tag."""

    if if_none_match is None:
        return False
    return any(_tag_matches(raw, etag) for raw in if_none_match.split(","))


def _tag_matches(raw: str, etag: str) -> bool:
    candidate = raw.strip()
    if candidate == "*":
        return True
    if candidate.startswith("W/"):
        candidate = candidate[2:]
    return candidate.strip('"') == etag


__all__ = ["validator_matches"]
