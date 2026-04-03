"""Thread-safe subprocess log collector.

Consolidates the LogCollector class previously duplicated across
test_e2e_url4.py, test_e2e_claude_frontend.py, and test_prompt_e2e.py.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time


class LogCollector:
    """Reads subprocess stdout in a background thread and stores lines."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.lines: list[str] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._read, args=(proc,), daemon=True)
        self._thread.start()

    def _read(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            with self._lock:
                self.lines.append(line)

    def wait_for_ready(self, timeout: float = 30) -> dict | None:
        """Block until the JSON ``{"event": "ready", ...}`` line appears."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                for line in self.lines:
                    if '"event"' in line and '"ready"' in line:
                        try:
                            return json.loads(line)
                        except json.JSONDecodeError:
                            continue
            time.sleep(0.3)
        return None

    def wait_for_line(self, needle: str, timeout: float = 10) -> str | None:
        """Block until a line containing *needle* appears."""
        deadline = time.monotonic() + timeout
        seen = 0
        while time.monotonic() < deadline:
            with self._lock:
                for line in self.lines[seen:]:
                    if needle in line:
                        return line
                seen = len(self.lines)
            time.sleep(0.2)
        return None

    def find_lines(self, needle: str) -> list[str]:
        """Return all lines containing *needle*."""
        with self._lock:
            return [line for line in self.lines if needle in line]

    def dump_all(self) -> list[str]:
        with self._lock:
            return list(self.lines)

    def dump_last(self, n: int = 20) -> list[str]:
        with self._lock:
            return list(self.lines[-n:])
