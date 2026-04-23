"""Shared persistence helpers for intercept-plugin state.

Several intercept plugins (``claude-intercept``, ``mitmproxy-intercept``,
…) each keep a tiny JSON blob on disk describing an in-flight mutation
to the host system that must survive a server crash: which /etc/hosts
lines were added, which PID owns the mitmproxy subprocess, when the
mutation began. Every implementation used to hand-roll the same five
functions (save/load/clear/is_stale/now_iso). This module owns them
once.

Each plugin defines its own dataclass (with whatever fields it needs —
domain list, subprocess port, hash of the original file, …) and
passes it in. The only invariants the helpers rely on are that the
state dataclass has an ``active: bool`` and a ``pid: int`` field.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def save_state(state: object, path: Path) -> None:
    """Persist a dataclass instance to ``path`` as pretty-printed JSON."""
    if not is_dataclass(state) or isinstance(state, type):
        msg = f"save_state expects a dataclass instance, got {type(state).__name__}"
        raise TypeError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
    logger.info("Intercept state saved to %s", path)


def load_state[T](state_cls: type[T], path: Path) -> T | None:
    """Load a dataclass from ``path``, or ``None`` if missing or corrupt."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return state_cls(**data)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Corrupt intercept state file %s: %s", path, exc)
        return None


def clear_state(path: Path) -> None:
    """Remove the state file if it exists."""
    if path.exists():
        path.unlink()
        logger.info("Intercept state cleared: %s", path)


def is_stale(state_cls: type, path: Path) -> bool:
    """True if a state file exists, is active, but its owning PID is dead."""
    state = load_state(state_cls, path)
    if state is None or not getattr(state, "active", False):
        return False
    pid = getattr(state, "pid", None)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # signal 0 = existence check
        return False  # process still running
    except ProcessLookupError:
        return True
    except PermissionError:
        return False  # exists but not ours to signal
