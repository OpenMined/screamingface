from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class PendingAuthEntry:
    account_id: str
    provider: str
    profile_name: str
    profile_id: str
    code_verifier: str


class PendingAuthTable:
    """In-memory CSRF-state store for pending OAuth flows. TTL-bounded."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[PendingAuthEntry, float]] = {}

    def put(self, state: str, entry: PendingAuthEntry) -> None:
        self._entries[state] = (entry, time.monotonic())

    def pop(self, state: str) -> PendingAuthEntry | None:
        item = self._entries.pop(state, None)
        if item is None:
            return None
        entry, ts = item
        if time.monotonic() - ts > self._ttl:
            return None
        return entry

    def peek(self, state: str) -> PendingAuthEntry | None:
        """Look up an entry without removing it. Returns None if expired."""
        item = self._entries.get(state)
        if item is None:
            return None
        entry, ts = item
        if time.monotonic() - ts > self._ttl:
            self._entries.pop(state, None)
            return None
        return entry
