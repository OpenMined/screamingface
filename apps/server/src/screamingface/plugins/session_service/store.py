"""FileSessionStore — JSONL-based session persistence.

Each session is a single JSONL file at {storage_dir}/{session_id}.jsonl:
- Line 1: SessionMetadata JSON
- Lines 2+: CanonicalMessage JSON (append-only)
"""

from __future__ import annotations

import fcntl
import logging
from datetime import UTC, datetime
from pathlib import Path

from screamingface.core.session import (
    CanonicalMessage,
    SessionMetadata,
    SessionStore,
)

logger = logging.getLogger(__name__)


class FileSessionStore(SessionStore):
    def __init__(self, storage_dir: str | Path) -> None:
        self._dir = Path(storage_dir).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        # Sanitize to prevent path traversal
        safe_id = session_id.replace("/", "").replace("..", "")
        return self._dir / f"{safe_id}.jsonl"

    def create(self, metadata: SessionMetadata) -> str:
        path = self._path(metadata.id)
        if path.exists():
            raise FileExistsError(f"Session {metadata.id} already exists")
        with open(path, "w") as f:
            f.write(metadata.model_dump_json() + "\n")
        return metadata.id

    def load_metadata(self, session_id: str) -> SessionMetadata:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        with open(path) as f:
            line = f.readline().strip()
        return SessionMetadata.model_validate_json(line)

    def load_messages(self, session_id: str) -> list[CanonicalMessage]:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        messages: list[CanonicalMessage] = []
        with open(path) as f:
            # Skip metadata line
            f.readline()
            for i, line in enumerate(f, start=2):
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(CanonicalMessage.model_validate_json(line))
                except Exception:
                    logger.warning("Skipping malformed line %d in session %s", i, session_id)
        return messages

    def append_message(self, session_id: str, message: CanonicalMessage) -> None:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        with open(path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(message.model_dump_json() + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        # Update metadata counts
        self._update_metadata(session_id)

    def _update_metadata(self, session_id: str) -> None:
        """Update message_count and updated_at in the metadata line."""
        path = self._path(session_id)
        with open(path) as f:
            lines = f.readlines()
        meta = SessionMetadata.model_validate_json(lines[0])
        meta.message_count += 1
        meta.updated_at = datetime.now(UTC)
        lines[0] = meta.model_dump_json() + "\n"
        with open(path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.writelines(lines)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[SessionMetadata]:
        sessions: list[SessionMetadata] = []
        paths = sorted(self._dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[offset : offset + limit]:
            try:
                with open(path) as f:
                    line = f.readline().strip()
                sessions.append(SessionMetadata.model_validate_json(line))
            except Exception:
                logger.warning("Skipping malformed session file: %s", path.name)
        return sessions

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        path.unlink()

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()
