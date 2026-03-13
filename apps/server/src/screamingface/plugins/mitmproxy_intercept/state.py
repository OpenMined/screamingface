"""Durable state for crash recovery of the mitmproxy-intercept plugin."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path("~/.screamingface/mitmproxy-intercept-state.json").expanduser()


@dataclass
class MitmproxyState:
    active: bool
    activated_at: str  # ISO timestamp
    pid: int  # mitmproxy subprocess PID
    proxy_port: int  # mitmproxy listen port
    domains: list[str]  # intercepted domains


def save_state(state: MitmproxyState) -> None:
    """Persist mitmproxy intercept state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(state), indent=2))
    logger.info("Mitmproxy intercept state saved to %s", STATE_FILE)


def load_state() -> MitmproxyState | None:
    """Load state from disk, or None if no state file."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return MitmproxyState(**data)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Corrupt mitmproxy intercept state file: %s", exc)
        return None


def clear_state() -> None:
    """Remove the state file."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        logger.info("Mitmproxy intercept state cleared")


def is_stale() -> bool:
    """Check if a state file exists but the mitmproxy process is dead."""
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
