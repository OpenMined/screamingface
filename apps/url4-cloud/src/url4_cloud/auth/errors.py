"""Typed token-verification failures (spec §4; docs/protocol.md §7).

INVARIANT: no subclass message ever embeds the token or the signing secret — these types are
raised on the request path and must be safe to surface (as an RFC 9457 detail) and to log.
"""


class AuthError(Exception):
    """Base class for a rejected capability token."""


class MissingCredentials(AuthError):
    """No capability token was presented."""


class InvalidToken(AuthError):
    """The token is malformed or its HS256 signature does not verify."""


class MissingIat(AuthError):
    """The token carries no ``iat`` claim, so the stateless window cannot be applied."""


class IatWindowExceeded(AuthError):
    """``now - iat`` exceeds the accepted issue window (the stateless freshness guard)."""


class TokenExpired(AuthError):
    """``now`` is at or past the token's ``exp``."""
