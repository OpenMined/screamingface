"""Shared helper for resolving the aigateway credential to forward from an inbound request.

Used by both ``routes.py`` (``GET /``) and ``catalog.py`` (``GET /v1/models``) so the two
endpoints parse the bearer scheme identically.

``Authorization: Bearer <token>`` is the ONLY credential source. url4-cloud verifies nothing
and holds no credential of its own — it forwards the caller's token and aigateway decides.
"""

from __future__ import annotations


def bearer_token(header: str | None) -> str | None:
    """Extract the token from an ``Authorization: Bearer <token>`` header value.

    Returns ``None`` if the header is absent, uses a non-Bearer scheme, or carries no token.
    """
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


__all__ = ["bearer_token"]
