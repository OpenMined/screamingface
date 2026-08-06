"""UI-independent state for the Engine connection panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from screamingface.connections import Connection

type PanelMode = Literal["methods", "api_key"]


@dataclass
class _ConnectionPanelState:
    """Mutable presentation state owned by one connection-panel controller."""

    hosted: bool
    connections: tuple[Connection, ...] = ()
    notice: str | None = None
    access_pending: bool = False
    access_check_pending: bool = False
    access_check_started: bool = False
    modes: dict[str, PanelMode] = field(default_factory=dict)
    flows: dict[str, object] = field(default_factory=dict)

    def access_status(self, *, authenticated: bool, authenticating: bool) -> str:
        if self.access_check_pending:
            status = "checking"
        elif self.access_pending or authenticating:
            status = "waiting"
        elif authenticated:
            status = "authenticated"
        else:
            status = "login_required"
        return status


def _is_hosted_engine(engine_url: str) -> bool:
    hostname = urlsplit(engine_url).hostname
    if hostname == "localhost":
        return False
    try:
        address = ip_address(hostname or "")
    except ValueError:
        return True
    return not (address.is_loopback or address.is_unspecified)


def _user_message(error: Exception) -> str:
    message = getattr(error, "user_message", None)
    return message if isinstance(message, str) else str(error)


__all__: list[str] = []
