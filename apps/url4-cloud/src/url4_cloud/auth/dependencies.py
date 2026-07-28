"""FastAPI capability-header dependency — verify the URL4-Capability token or 401 (spec §4;
docs/protocol.md §7)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from url4_cloud.auth.errors import AuthError, MissingCredentials
from url4_cloud.auth.jwt import JwtCodec
from url4_cloud.auth.problem import ProblemException
from url4_cloud.config import Settings

Clock = Callable[[], datetime]
_CAPABILITY_HEADER = "URL4-Capability"


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _extract_capability(request: Request) -> str:
    # WHY: the per-run capability rides a dedicated header (RFC 6648-clean, no `X-`; RFC 9449
    # DPoP-style secondary credential), decoupled from `Authorization` so a gateway/mesh/SDK that
    # owns the primary identity slot cannot strip or overwrite it (OME-556). Bare JWT, no scheme.
    token = request.headers.get(_CAPABILITY_HEADER)
    if not token:
        raise MissingCredentials("missing capability credentials")
    return token.strip()


def verified_claims(request: Request) -> dict[str, object]:
    """Verify the request's URL4-Capability token; raise 401 problem+json on any failure.

    The signing config comes from ``app.state.settings`` and the clock from ``app.state.clock``
    (falling back to a UTC wall clock), so both are injectable for tests without patching.
    SECURITY: the token and the secret are never logged nor echoed in the error body.
    """
    settings: Settings = request.app.state.settings
    clock: Clock = getattr(request.app.state, "clock", _default_clock)
    codec = JwtCodec(secret=settings.jwt_secret, iat_window_s=settings.iat_window_s)
    try:
        token = _extract_capability(request)
        return codec.verify(token, clock())
    except AuthError as exc:
        # WHY: one opaque reason for every failure — no oracle revealing which check failed. No
        # WWW-Authenticate header: that RFC 7235 challenge is bound to `Authorization`, which we
        # deliberately do not use for the capability (OME-556).
        raise ProblemException(
            status=401,
            title="Unauthorized",
            detail="missing, invalid, or expired capability token",
        ) from exc


VerifiedClaims = Annotated[dict[str, object], Depends(verified_claims)]
