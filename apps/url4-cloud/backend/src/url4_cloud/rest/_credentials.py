"""Resolving the aigateway credential a request forwards (plan §5.3 dec:A; spec §4).

FEATURE: identity forwarding. Two entry points need the SAME answer to "which credential does this
request carry?" — ``GET /?q=`` (which forwards it into the run) and ``GET /v1/models`` (which
forwards it upstream to fetch the catalog).

AIDEV-NOTE: extracted from ``rest.routes`` when the catalog endpoint arrived (OME-625). Keep it
shared: if these two endpoints ever disagree about precedence, a caller could get a catalog for one
identity and a run executed under another — a confusing, hard-to-see bug. url4-cloud verifies
neither value; aigateway, the actual consumer, verifies whichever one arrives.
"""

from __future__ import annotations


def bearer_token(header: str | None) -> str | None:
    """The token from a ``Bearer <token>`` ``Authorization`` header, case-insensitive scheme.

    Absent header, a non-Bearer scheme, or an empty token → ``None`` (never forward garbage —
    mirrors the ``traceparent`` malformed-input rule).
    """
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    token = token.strip()  # a multi-space "Bearer  <tok>" must not forward a leading-space token
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def forwarded_credential(authorization: str | None, cf_access_jwt: str | None) -> str | None:
    """The aigateway credential to forward — a Cloudflare Access session JWT, when present, else a
    client-supplied ``Authorization: Bearer`` token (plan §5.3 dec:A extension).

    WHY Cloudflare Access wins: it is attached by the edge itself once a browser has completed OTP
    login — the "you are logged in" signal — with no client code involved. A client-supplied
    ``Authorization`` header stays available as the fallback for direct/service callers that never
    go through Cloudflare Access.
    """
    if cf_access_jwt:
        return cf_access_jwt
    return bearer_token(authorization)


__all__ = ["bearer_token", "forwarded_credential"]
