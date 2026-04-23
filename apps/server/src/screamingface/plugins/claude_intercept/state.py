"""Durable state for crash recovery of the claude-intercept plugin."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from screamingface.core.intercept_state import (
    clear_state as _clear_state,
)
from screamingface.core.intercept_state import (
    is_stale as _is_stale,
)
from screamingface.core.intercept_state import (
    load_state as _load_state,
)
from screamingface.core.intercept_state import (
    now_iso,
)
from screamingface.core.intercept_state import (
    save_state as _save_state,
)

__all__ = [
    "HOSTS_FILE",
    "InterceptState",
    "STATE_FILE",
    "clear_state",
    "hosts_hash",
    "is_stale",
    "load_state",
    "now_iso",
    "save_state",
]

STATE_FILE = Path("~/.screamingface/claude-intercept-state.json").expanduser()
HOSTS_FILE = Path("/etc/hosts")


@dataclass
class InterceptState:
    active: bool
    activated_at: str  # ISO timestamp
    domains: list[str]
    original_hosts_hash: str  # SHA256 of /etc/hosts before modification
    pid: int  # server PID that activated
    real_ips: dict[str, str] | None = None  # domain → real IP (persisted across reloads)


def save_state(state: InterceptState) -> None:
    _save_state(state, STATE_FILE)


def load_state() -> InterceptState | None:
    return _load_state(InterceptState, STATE_FILE)


def clear_state() -> None:
    _clear_state(STATE_FILE)


def is_stale() -> bool:
    return _is_stale(InterceptState, STATE_FILE)


def hosts_hash() -> str:
    """Return SHA256 hex digest of current /etc/hosts."""
    return hashlib.sha256(HOSTS_FILE.read_bytes()).hexdigest()
