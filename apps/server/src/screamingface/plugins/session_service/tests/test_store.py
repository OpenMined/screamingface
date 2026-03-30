"""Tests for FileSessionStore — JSONL session persistence."""

from __future__ import annotations

import pytest

from screamingface.plugins.session_service.models import (
    CanonicalMessage,
    SessionMetadata,
    TextContent,
)
from screamingface.plugins.session_service.store import FileSessionStore


@pytest.fixture
def store(tmp_path) -> FileSessionStore:
    return FileSessionStore(tmp_path / "sessions")


@pytest.fixture
def session_id(store: FileSessionStore) -> str:
    meta = SessionMetadata(title="test")
    return store.create(meta)


class TestCreate:
    def test_creates_file(self, store: FileSessionStore) -> None:
        meta = SessionMetadata(title="my session")
        sid = store.create(meta)
        assert store.exists(sid)

    def test_duplicate_raises(self, store: FileSessionStore) -> None:
        meta = SessionMetadata(title="dup")
        store.create(meta)
        with pytest.raises(FileExistsError):
            store.create(meta)


class TestLoadMetadata:
    def test_round_trip(self, store: FileSessionStore) -> None:
        meta = SessionMetadata(title="round trip", tags=["test"])
        sid = store.create(meta)
        loaded = store.load_metadata(sid)
        assert loaded.title == "round trip"
        assert loaded.tags == ["test"]
        assert loaded.id == sid

    def test_not_found(self, store: FileSessionStore) -> None:
        with pytest.raises(FileNotFoundError):
            store.load_metadata("nonexistent")


class TestMessages:
    def test_append_and_load(self, store: FileSessionStore, session_id: str) -> None:
        msg = CanonicalMessage(role="user", content=[TextContent(text="hello")])
        store.append_message(session_id, msg)

        messages = store.load_messages(session_id)
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content[0].text == "hello"  # type: ignore[union-attr]

    def test_multiple_messages(self, store: FileSessionStore, session_id: str) -> None:
        for i in range(3):
            role = "user" if i % 2 == 0 else "assistant"
            msg = CanonicalMessage(role=role, content=[TextContent(text=f"msg {i}")])
            store.append_message(session_id, msg)

        messages = store.load_messages(session_id)
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[2].role == "user"

    def test_empty_session(self, store: FileSessionStore, session_id: str) -> None:
        messages = store.load_messages(session_id)
        assert messages == []

    def test_append_not_found(self, store: FileSessionStore) -> None:
        msg = CanonicalMessage(role="user", content=[TextContent(text="hi")])
        with pytest.raises(FileNotFoundError):
            store.append_message("nonexistent", msg)

    def test_metadata_updated_after_append(self, store: FileSessionStore, session_id: str) -> None:
        msg = CanonicalMessage(role="user", content=[TextContent(text="hi")])
        store.append_message(session_id, msg)

        meta = store.load_metadata(session_id)
        assert meta.message_count == 1

    def test_malformed_line_skipped(self, store: FileSessionStore, session_id: str) -> None:
        # Append a valid message then corrupt the file
        msg = CanonicalMessage(role="user", content=[TextContent(text="valid")])
        store.append_message(session_id, msg)

        path = store._path(session_id)
        with open(path, "a") as f:
            f.write("not valid json\n")

        msg2 = CanonicalMessage(role="assistant", content=[TextContent(text="also valid")])
        store.append_message(session_id, msg2)

        messages = store.load_messages(session_id)
        assert len(messages) == 2  # skipped the bad line


class TestListAndDelete:
    def test_list_sessions(self, store: FileSessionStore) -> None:
        for i in range(3):
            store.create(SessionMetadata(title=f"session {i}"))
        sessions = store.list_sessions()
        assert len(sessions) == 3

    def test_list_with_limit(self, store: FileSessionStore) -> None:
        for i in range(5):
            store.create(SessionMetadata(title=f"session {i}"))
        sessions = store.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_delete(self, store: FileSessionStore, session_id: str) -> None:
        assert store.exists(session_id)
        store.delete(session_id)
        assert not store.exists(session_id)

    def test_delete_not_found(self, store: FileSessionStore) -> None:
        with pytest.raises(FileNotFoundError):
            store.delete("nonexistent")
