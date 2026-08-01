"""Provider-connection subsystem and production composition helper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

from url4_cloud.connections.aigateway import AigatewayConnections
from url4_cloud.connections.port import (
    Caller,
    Connection,
    ConnectionBadResponse,
    ConnectionConflict,
    ConnectionError,
    ConnectionNotFound,
    ConnectionRateLimited,
    ConnectionRejected,
    Connections,
    ConnectionUnavailable,
)

_UPSTREAM_TIMEOUT_S = 10.0


class _ConnectionSettings(Protocol):
    aigateway_base_url: str | None


def _default_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=_UPSTREAM_TIMEOUT_S)


def build_connections(
    settings: _ConnectionSettings,
    *,
    client_factory: Callable[[str], httpx.AsyncClient] = _default_client,
) -> AigatewayConnections | None:
    """Build the AI Gateway adapter, or disable the endpoints when no upstream is configured."""

    if not settings.aigateway_base_url:
        return None
    return AigatewayConnections(client_factory(settings.aigateway_base_url))


__all__ = [
    "AigatewayConnections",
    "Caller",
    "Connection",
    "ConnectionBadResponse",
    "ConnectionConflict",
    "ConnectionError",
    "ConnectionNotFound",
    "ConnectionRateLimited",
    "ConnectionRejected",
    "ConnectionUnavailable",
    "Connections",
    "build_connections",
]
