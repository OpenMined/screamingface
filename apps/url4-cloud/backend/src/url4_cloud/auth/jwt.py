"""HS256 capability-token codec — RFC 7519 registered claims (spec §4; docs/protocol.md §7)."""

import secrets
from dataclasses import dataclass
from datetime import datetime

import jwt as pyjwt

from url4_cloud.auth.errors import (
    IatWindowExceeded,
    InvalidToken,
    MissingIat,
    TokenExpired,
)

_ALGORITHM = "HS256"
_JTI_BYTES = 16


@dataclass(frozen=True)
class JwtCodec:
    """Signs and verifies the per-run capability JWT.

    Bound to a single ``secret`` and ``iat_window_s`` so callers cannot mix acceptance windows.
    The clock is always **injected** (``now``) — verification is deterministic and never reads
    wall-clock time, so the stateless freshness guard is testable and reproducible.
    """

    secret: str
    iat_window_s: int

    def sign(self, topic: str, now: datetime) -> str:
        """Mint a token binding ``topic`` (``sub``); ``exp = iat + iat_window_s`` plus a ``jti``."""
        iat = int(now.timestamp())
        payload = {
            "sub": topic,
            "iat": iat,
            "exp": iat + self.iat_window_s,
            "jti": secrets.token_hex(_JTI_BYTES),
        }
        return pyjwt.encode(payload, self.secret, algorithm=_ALGORITHM)

    def verify(self, token: str, now: datetime) -> dict[str, object]:
        """Return the claims, or raise a typed :mod:`errors` failure.

        Signature is checked by PyJWT; time is checked here against the injected ``now`` so the
        result does not depend on the process clock (docs/protocol.md §7 "belt-and-suspenders").
        """
        try:
            # WHY: verify_exp off — PyJWT would use wall-clock; we enforce exp below vs `now`.
            claims = pyjwt.decode(
                token, self.secret, algorithms=[_ALGORITHM], options={"verify_exp": False}
            )
        except pyjwt.InvalidTokenError as exc:
            raise InvalidToken("token is malformed or its signature is invalid") from exc

        if "iat" not in claims:
            raise MissingIat("token has no iat claim")
        now_s = int(now.timestamp())
        iat = int(claims["iat"])
        if now_s - iat > self.iat_window_s:
            raise IatWindowExceeded("token iat is outside the acceptance window")
        exp = claims.get("exp")
        # INVARIANT: valid requires now < exp (RFC 7519); at now == exp the token is expired.
        if exp is not None and now_s >= int(exp):
            raise TokenExpired("token has expired")
        return claims
