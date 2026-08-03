"""Public provider-connection values and default-client convenience functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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


def list() -> tuple[Connection, ...]:
    """List connections through the lazy default Client."""

    from screamingface._default_client import default_client

    return default_client().connections.list()


def get(provider: str) -> Connection:
    """Get one connection through the lazy default Client."""

    from screamingface._default_client import default_client

    return default_client().connections.get(provider)


__all__ = ["Connection", "ConnectionStatus", "get", "list"]
