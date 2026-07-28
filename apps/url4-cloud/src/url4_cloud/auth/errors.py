"""Exception hierarchy for capability-token authentication failures.

``MissingCredentials`` is raised in :func:`url4_cloud.auth.dependencies._extract_capability`
when a request carries no capability header at all; :class:`url4_cloud.auth.jwt.JwtCodec`
never sees that case. The other four subclasses are raised by
:meth:`url4_cloud.auth.jwt.JwtCodec.verify` for the ways a present token can fail
verification. `dependencies.verified_claims` catches ``AuthError`` and translates it
into a 401 RFC 9457 problem response, so these are internal signals, not something
clients see directly.

INVARIANT: no subclass message ever embeds the token or the signing secret — these types are
raised on the request path and must be safe to surface (as an RFC 9457 detail) and to log.
"""


class AuthError(Exception):
    """Base class for all capability-token authentication failures."""


class MissingCredentials(AuthError):
    """Raised when a request carries no capability token at all."""


class InvalidToken(AuthError):
    """Raised when the token is malformed or its signature does not verify."""


class MissingIat(AuthError):
    """Raised when the token has no ``iat`` (issued-at) claim."""


class IatWindowExceeded(AuthError):
    """Raised when the token's ``iat`` is older than the configured acceptance window."""


class TokenExpired(AuthError):
    """Raised when the token's ``exp`` claim has passed."""
