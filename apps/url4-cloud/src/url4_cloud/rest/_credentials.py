"""Shared helper for resolving the aigateway credential to forward from an inbound request.

Used by both ``routes.py`` (``GET /``) and ``catalog.py`` (``GET /v1/models``) so the two
endpoints agree on which header wins and how a bearer scheme is parsed.
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


def forwarded_credential(authorization: str | None, cf_access_jwt: str | None) -> str | None:
    """Pick the aigateway credential to forward: ``Cf-Access-Jwt-Assertion`` over ``Authorization``.

    Returns ``None`` when neither header supplies a usable credential — callers then treat the
    run/request as unauthenticated toward aigateway.
    """
    if cf_access_jwt:
        # WHY: Cf-Access-Jwt-Assertion is attached by the Cloudflare Access edge, not the
        # client, so it is trusted ahead of a client-supplied Authorization header, ON THE
        # PRECONDITION that this deployment's ingress guarantees all traffic transits CF
        # Access (nothing in this code verifies that or strips a client-forged copy of this
        # header — that's an edge/network-topology guarantee, not a code-level one).
        return cf_access_jwt
    return bearer_token(authorization)


__all__ = ["bearer_token", "forwarded_credential"]
