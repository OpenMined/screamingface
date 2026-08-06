"""Shared Client origin, auth-listener, and provider-connection support."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

from screamingface.errors import ProviderConnectionError

if TYPE_CHECKING:
    from screamingface._engine.connections import AsyncConnections, Connections
    from screamingface.connections import AsyncOAuthFlow, Connection, OAuthFlow


class _AuthListeners:
    """Thread-safe observer set shared by the sync and async Client facades."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._callbacks: set[Callable[[], None]] = set()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            self._callbacks.add(callback)

        def unsubscribe() -> None:
            with self._lock:
                self._callbacks.discard(callback)

        return unsubscribe

    def notify(self) -> None:
        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            callback()


def _engine_origin(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("engine_url must be an HTTP(S) origin")
    parts = urlsplit(value.strip())
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("engine_url must be an HTTP(S) origin without credentials or a path")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _require_secure_connection_origin(engine_url: str) -> None:
    parts = urlsplit(engine_url)
    if parts.scheme == "https" or (
        parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        return
    raise ProviderConnectionError(
        "Provider connection operations require HTTPS outside a loopback SF Engine",
        code="secure_transport_required",
        permanent=True,
    )


def _connect_sync(
    connections: Connections,
    provider: str,
    api_key: str | None,
    method: Literal["api_key", "oauth"] | None,
) -> Connection | OAuthFlow:
    _validate_auth_method(method)
    if api_key is not None:
        _require_api_key_action(method)
        return connections.connect(provider, api_key)
    if method == "api_key":
        raise ValueError("api_key is required for API-key authentication")
    if method == "oauth":
        return connections.start_oauth(provider)
    raise ValueError("api_key is required unless method='oauth' is selected")


async def _connect_async(
    connections: AsyncConnections,
    provider: str,
    api_key: str | None,
    method: Literal["api_key", "oauth"] | None,
) -> Connection | AsyncOAuthFlow:
    _validate_auth_method(method)
    if api_key is not None:
        _require_api_key_action(method)
        return await connections.connect(provider, api_key)
    if method == "api_key":
        raise ValueError("api_key is required for API-key authentication")
    if method == "oauth":
        return await connections.start_oauth(provider)
    raise ValueError("api_key is required unless method='oauth' is selected")


def _validate_auth_method(method: object) -> None:
    if method not in {None, "api_key", "oauth"}:
        raise ValueError("method must be 'api_key', 'oauth', or None")


def _require_api_key_action(method: object) -> None:
    if method == "oauth":
        raise ValueError("api_key cannot be combined with OAuth")


__all__: list[str] = []
