"""FastAPI Bearer dependency — verify the capability token or 401 (spec §4; docs/protocol.md §7)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from url4_cloud.auth.errors import AuthError, MissingCredentials
from url4_cloud.auth.jwt import JwtCodec
from url4_cloud.auth.problem import ProblemException
from url4_cloud.config import Settings

Clock = Callable[[], datetime]
_BEARER_PREFIX = "Bearer "


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization")
    if header is None or not header.startswith(_BEARER_PREFIX):
        raise MissingCredentials("missing Bearer credentials")
    return header[len(_BEARER_PREFIX) :].strip()


def verified_claims(request: Request) -> dict[str, object]:
    """Verify the request's Bearer capability token; raise 401 problem+json on any failure.

    The signing config comes from ``app.state.settings`` and the clock from ``app.state.clock``
    (falling back to a UTC wall clock), so both are injectable for tests without patching.
    SECURITY: the token and the secret are never logged nor echoed in the error body.
    """
    settings: Settings = request.app.state.settings
    clock: Clock = getattr(request.app.state, "clock", _default_clock)
    codec = JwtCodec(secret=settings.jwt_secret, iat_window_s=settings.iat_window_s)
    try:
        token = _extract_bearer(request)
        return codec.verify(token, clock())
    except AuthError as exc:
        # WHY: one opaque reason for every failure — no oracle revealing which check failed.
        raise ProblemException(
            status=401,
            title="Unauthorized",
            detail="missing, invalid, or expired capability token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


VerifiedClaims = Annotated[dict[str, object], Depends(verified_claims)]
