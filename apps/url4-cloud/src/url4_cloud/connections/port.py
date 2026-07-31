"""Provider-connection domain types and the Engine-facing port.

The control plane exposes connection state without exposing aigateway's account IDs,
credential locators, or provider response bodies. Concrete adapters translate their
upstream into these deliberately small values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

AuthMethod = Literal["api_key", "oauth"]
ConnectionStatus = Literal[
    "not_connected",
    "pending",
    "connected",
    "needs_reauth",
    "error",
]


@dataclass(frozen=True, slots=True)
class Caller:
    """Verified identity headers associated with one Engine request."""

    identity: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Connection:
    """The safe, public status of one provider connection."""

    provider: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]
    status: ConnectionStatus
    auth_method: AuthMethod | None = None
    account_label: str | None = None

    @classmethod
    def openrouter(
        cls,
        *,
        status: ConnectionStatus = "not_connected",
        auth_method: AuthMethod | None = None,
        account_label: str | None = None,
    ) -> Connection:
        return cls(
            provider="openrouter",
            display_name="OpenRouter",
            auth_methods=("api_key",),
            status=status,
            auth_method=auth_method,
            account_label=account_label,
        )


class ConnectionError(Exception):
    """A safe connection failure with its public HTTP mapping."""

    status = 502
    title = "Bad Gateway"
    detail = "the provider connection could not be updated"

    def __init__(self, detail: str | None = None) -> None:
        # Accepting a caller message is useful for logs/tests, but public routes always use
        # the class-level safe detail. This prevents an upstream body or API key from leaking.
        self.internal_detail = detail
        super().__init__(self.detail)


class ConnectionRejected(ConnectionError):
    """The caller identity or provider credential was rejected."""

    status = 401
    title = "Unauthorized"
    detail = "the provider connection was rejected"


class ConnectionNotFound(ConnectionError):
    """The requested provider is not exposed by this Engine."""

    status = 404
    title = "Not Found"
    detail = "the requested provider is not available"


class ConnectionConflict(ConnectionError):
    """More than one upstream connection exists and none is the managed row."""

    status = 409
    title = "Conflict"
    detail = "multiple provider connections exist; choose one in AI Gateway"


class ConnectionRateLimited(ConnectionError):
    """AI Gateway refused the operation because it was rate limited."""

    status = 429
    title = "Too Many Requests"
    detail = "provider connection requests are temporarily rate limited"


class ConnectionBadResponse(ConnectionError):
    """AI Gateway returned a malformed or otherwise unusable response."""

    status = 502
    title = "Bad Gateway"
    detail = "AI Gateway returned an unusable provider connection response"


class ConnectionUnavailable(ConnectionError):
    """AI Gateway did not respond before the Engine timeout."""

    status = 504
    title = "Gateway Timeout"
    detail = "AI Gateway did not respond in time"


@runtime_checkable
class Connections(Protocol):
    """Provider-connection operations required by the Engine REST surface."""

    async def list(self, caller: Caller) -> tuple[Connection, ...]: ...

    async def connect(self, caller: Caller, provider: str, api_key: str) -> Connection: ...

    async def disconnect(self, caller: Caller, provider: str) -> Connection: ...


__all__ = [
    "AuthMethod",
    "Caller",
    "Connection",
    "ConnectionBadResponse",
    "ConnectionConflict",
    "ConnectionError",
    "ConnectionNotFound",
    "ConnectionRateLimited",
    "ConnectionRejected",
    "ConnectionStatus",
    "ConnectionUnavailable",
    "Connections",
]
