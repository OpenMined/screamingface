import time

import pytest

from aigateway.core.pending_auth import PendingAuthEntry, PendingAuthTable


def test_pending_table_round_trip() -> None:
    table = PendingAuthTable(ttl_seconds=600)
    table.put("state-1", PendingAuthEntry(profile_id="anthropic:work", code_verifier="v"))
    entry = table.pop("state-1")
    assert entry is not None
    assert entry.profile_id == "anthropic:work"
    assert entry.code_verifier == "v"


def test_pop_consumes_entry() -> None:
    table = PendingAuthTable(ttl_seconds=600)
    table.put("state-1", PendingAuthEntry(profile_id="anthropic:work", code_verifier="v"))
    table.pop("state-1")
    assert table.pop("state-1") is None  # second pop is a miss


def test_expired_entry_is_swept(monkeypatch) -> None:
    fake = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake["now"])
    table = PendingAuthTable(ttl_seconds=10)
    table.put("state-1", PendingAuthEntry(profile_id="anthropic:work", code_verifier="v"))
    fake["now"] = 1100.0  # 100s later
    assert table.pop("state-1") is None


def test_unknown_state_returns_none() -> None:
    table = PendingAuthTable(ttl_seconds=600)
    assert table.pop("nonexistent") is None
