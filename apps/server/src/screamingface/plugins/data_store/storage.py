"""In-process blob storage backing the data-store plugin.

Owned by the plugin: every running app gets its own ``BlobStore`` on
``app.state.blob_store`` (set in :meth:`DataStorePlugin.setup`). Other
plugins reach it via ``request.app.state.blob_store`` from FastAPI
handlers, or via the ``app`` they receive in their own ``setup``.

Thread-safe: the underlying dict is guarded by a ``threading.Lock``
because frontends occasionally call ``store(...)`` from synchronous
threads (``_fetch_sync`` in each frontend plugin) while the routes
access it from the async event loop.
"""

from __future__ import annotations

import hashlib
import threading

__all__ = ["BlobStore"]


class BlobStore:
    """Thread-safe, content-addressed byte store.

    ``store(data)`` returns a stable 16-hex-char content hash as the
    key. ``get(key)`` returns ``(bytes, content_type)`` or ``None``.
    Unbounded — callers are expected to keep entries small (prompt
    blobs, resolver payloads) and let the process lifetime bound it.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[bytes, str]] = {}
        self._lock = threading.Lock()

    def store(self, data: bytes, content_type: str = "application/octet-stream") -> str:
        key = hashlib.sha256(data).hexdigest()[:16]
        with self._lock:
            self._entries[key] = (data, content_type)
        return key

    def get(self, key: str) -> tuple[bytes, str] | None:
        with self._lock:
            return self._entries.get(key)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
