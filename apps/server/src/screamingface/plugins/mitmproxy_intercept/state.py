"""Durable state for crash recovery of the mitmproxy-intercept plugin."""

from __future__ import annotations

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
    "MitmproxyState",
    "STATE_FILE",
    "clear_state",
    "is_stale",
    "load_state",
    "now_iso",
    "save_state",
]

STATE_FILE = Path("~/.screamingface/mitmproxy-intercept-state.json").expanduser()


@dataclass
class MitmproxyState:
    active: bool
    activated_at: str  # ISO timestamp
    pid: int  # mitmproxy subprocess PID
    proxy_port: int  # mitmproxy listen port


def save_state(state: MitmproxyState) -> None:
    _save_state(state, STATE_FILE)


def load_state() -> MitmproxyState | None:
    return _load_state(MitmproxyState, STATE_FILE)


def clear_state() -> None:
    _clear_state(STATE_FILE)


def is_stale() -> bool:
    return _is_stale(MitmproxyState, STATE_FILE)
