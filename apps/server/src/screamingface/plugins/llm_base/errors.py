"""Error hierarchy for llm-base and its consumers.

All errors inherit from :class:`LlmBaseError` so callers can catch the
whole family with one ``except`` clause. Specific subclasses exist for
the common failure modes so callers can differentiate when they need to.
"""

from __future__ import annotations


class LlmBaseError(Exception):
    """Base class for every error raised by llm-base or its consumers."""


class CredentialNotFoundError(LlmBaseError):
    """Raised when a credential store doesn't have the requested entry.

    Distinguished from :class:`AuthError` because this is a "user hasn't
    authenticated yet" state, not a "token is broken" state. The typical
    user action is to run the provider's CLI login command (e.g.
    ``claude auth login``).
    """


class AuthError(LlmBaseError):
    """Raised when authentication fails in a way the user must fix.

    Covers: refresh token expired / invalidated, OAuth scope rejected,
    refresh endpoint returning 401 or ``invalid_grant``. The typical
    user action is also to re-run the provider's CLI login command, but
    the cause is a broken existing credential rather than an absent one.
    """


class AdapterError(LlmBaseError):
    """Raised when an :class:`Adapter` cannot convert between shapes.

    Typically means the input CoreMessage list contains a construct the
    target provider cannot represent (e.g. a content block type the
    adapter doesn't support, or a tool_use/tool_result pairing that
    would produce an invalid provider-side request).
    """


class BackendError(LlmBaseError):
    """Raised when a :class:`Backend` call fails at the transport level.

    Covers: provider HTTP 4xx/5xx responses (other than 401/403 which
    become :class:`AuthError`), network failures, timeouts, malformed
    responses. Carries the HTTP status code and optional retry-after
    hint as attributes.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
