"""Conditional-request handling shared by the REST catalogs (RFC 9110 §13.1.2).

WHY this is one module rather than a copy per route: `If-None-Match` comparison is a spec rule,
not a per-route preference. Two implementations of it drift — and they had already begun to,
holding the ETag in different shapes (one bare, one pre-quoted) purely because each matcher was
written against its own producer.

INVARIANT: an ETag is stored and compared UNQUOTED, and quoted only where it is written to a
header. The quotes are wire syntax; carrying them in the value makes every comparison site
responsible for stripping them, which is the drift this module exists to prevent.
"""

from __future__ import annotations


def validator_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 §13.1.2 weak comparison of an ``If-None-Match`` list against our ETag.

    WHY weak: the RFC mandates weak comparison for ``If-None-Match``, so a ``W/``-prefixed tag
    added by an intermediary must still register as a match — otherwise a client behind such a
    proxy would re-download the representation on every poll.

    ``etag`` is the bare validator, without quotes.
    """
    if if_none_match is None:
        return False
    return any(_tag_matches(raw, etag) for raw in if_none_match.split(","))


def _tag_matches(raw: str, etag: str) -> bool:
    """One entity-tag from an ``If-None-Match`` list, compared weakly."""
    candidate = raw.strip()
    if candidate == "*":
        return True
    if candidate.startswith("W/"):
        candidate = candidate[2:]
    return candidate.strip('"') == etag


__all__ = ["validator_matches"]
