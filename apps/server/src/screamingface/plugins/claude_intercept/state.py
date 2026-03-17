"""Durable state for crash recovery of the claude-intercept plugin."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

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
    """Persist intercept state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(state), indent=2))
    logger.info("Intercept state saved to %s", STATE_FILE)


def load_state() -> InterceptState | None:
    """Load intercept state from disk, or None if no state file."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return InterceptState(**data)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Corrupt intercept state file: %s", exc)
        return None


def clear_state() -> None:
    """Remove the state file."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        logger.info("Intercept state cleared")


def is_stale() -> bool:
    """Check if a state file exists but the owning process is dead."""
    state = load_state()
    if state is None or not state.active:
        return False
    try:
        os.kill(state.pid, 0)  # signal 0 = check if process exists
        return False  # process is still running
    except ProcessLookupError:
        return True  # PID is dead → stale
    except PermissionError:
        return False  # process exists but we can't signal it


def now_iso() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(UTC).isoformat()


def hosts_hash() -> str:
    """Return SHA256 hex digest of current /etc/hosts."""
    return hashlib.sha256(HOSTS_FILE.read_bytes()).hexdigest()
