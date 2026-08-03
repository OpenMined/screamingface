"""Public provider-connection values and default-client convenience functions."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from screamingface.errors import ProviderConnectionError

type AuthMethod = Literal["api_key", "oauth"]
type ConnectionStatus = Literal[
    "not_connected",
    "pending",
    "connected",
    "needs_reauth",
    "error",
]

_METHODS = frozenset({"api_key", "oauth"})
_STATUSES = frozenset({"not_connected", "pending", "connected", "needs_reauth", "error"})


@dataclass(frozen=True, slots=True)
class Connection:
    """Sanitized provider state advertised by the configured SF Engine."""

    provider: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]
    status: ConnectionStatus
    auth_method: AuthMethod | None
    account_label: str | None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.display_name.strip():
            raise ValueError("connection provider and display_name must be non-empty")
        if not self.auth_methods or any(method not in _METHODS for method in self.auth_methods):
            raise ValueError("connection auth_methods contain an unsupported method")
        if self.status not in _STATUSES:
            raise ValueError(f"unknown connection status {self.status!r}")
        if self.auth_method is not None and self.auth_method not in self.auth_methods:
            raise ValueError("connection auth_method is not advertised by its provider")
        if self.account_label is not None and not self.account_label.strip():
            raise ValueError("connection account_label must be non-empty or None")


@dataclass(frozen=True, slots=True)
class OAuthFlow:
    """A bounded provider OAuth authorization started through one Client."""

    provider: str
    authorize_url: str
    expires_in: int
    status: Literal["pending"] = "pending"
    _get: Callable[[], Connection] | None = field(default=None, repr=False, compare=False)
    _disconnect: Callable[[], Connection] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _expires_at: float = field(default=0.0, repr=False, compare=False)

    def wait(self, *, poll_interval: float = 0.5) -> Connection:
        """Block until authorization completes or the bounded flow expires."""

        interval = _poll_interval(poll_interval)
        get = _required_callback(self._get)
        while time.monotonic() <= self._expires_at:
            connection = get()
            if connection.status != "pending":
                return connection
            time.sleep(interval)
        raise _expired(self.provider)

    def cancel(self) -> Connection:
        """Cancel this authorization; repeated cancellation remains harmless."""

        return _required_callback(self._disconnect)()

    @property
    def expired(self) -> bool:
        """Whether the Engine-advertised authorization lifetime has elapsed."""

        return time.monotonic() > self._expires_at


@dataclass(frozen=True, slots=True)
class AsyncOAuthFlow:
    """Asynchronous counterpart of :class:`OAuthFlow`."""

    provider: str
    authorize_url: str
    expires_in: int
    status: Literal["pending"] = "pending"
    _get: Callable[[], Awaitable[Connection]] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _disconnect: Callable[[], Awaitable[Connection]] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _expires_at: float = field(default=0.0, repr=False, compare=False)

    async def wait(self, *, poll_interval: float = 0.5) -> Connection:
        """Wait asynchronously until authorization completes or expires."""

        interval = _poll_interval(poll_interval)
        get = _required_callback(self._get)
        while time.monotonic() <= self._expires_at:
            connection = await get()
            if connection.status != "pending":
                return connection
            await asyncio.sleep(interval)
        raise _expired(self.provider)

    async def cancel(self) -> Connection:
        """Cancel this authorization; repeated cancellation remains harmless."""

        return await _required_callback(self._disconnect)()

    @property
    def expired(self) -> bool:
        """Whether the Engine-advertised authorization lifetime has elapsed."""

        return time.monotonic() > self._expires_at


def _poll_interval(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("poll_interval must be a non-negative number")
    if value < 0:
        raise ValueError("poll_interval must be a non-negative number")
    return float(value)


def _required_callback[T](callback: T | None) -> T:
    if callback is None:
        raise ValueError("OAuth flow values are created by Client.connect(..., method='oauth')")
    return callback


def _expired(provider: str) -> ProviderConnectionError:
    return ProviderConnectionError(
        f"OAuth authorization for {provider!r} expired",
        provider=provider,
        code="oauth_authorization_expired",
        permanent=False,
    )


def list() -> tuple[Connection, ...]:
    """List connections through the lazy default Client."""

    from screamingface._default_client import default_client

    return default_client().connections.list()


def get(provider: str) -> Connection:
    """Get one connection through the lazy default Client."""

    from screamingface._default_client import default_client

    return default_client().connections.get(provider)


__all__ = [
    "AsyncOAuthFlow",
    "Connection",
    "ConnectionStatus",
    "OAuthFlow",
    "get",
    "list",
]
