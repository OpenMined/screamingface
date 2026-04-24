"""In-process blob storage backing the data-store plugin.

Split out of :mod:`.routes` in SF-112 so that other plugins can import
``store_blob`` / ``get_blob`` without reaching into a ``.routes``
module (which is an implementation detail of the FastAPI layer).

Thread-safe: the underlying dict is guarded by a ``threading.Lock``
because frontends occasionally call ``store_blob`` from synchronous
threads (``_fetch_sync`` in each frontend plugin) while the routes
access it from the async event loop.
"""

from __future__ import annotations

import hashlib
import threading

__all__ = ["BlobStore", "get_blob", "store_blob"]


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


# Module-level singleton. Kept because the in-process fallback path
# (frontends calling store_blob without going through HTTP) needs a
# shared instance — and there's exactly one data-store plugin per
# server. ``app.state`` would be cleaner but requires plumbing `app`
# through every caller; this is a pragmatic middle ground.
_default_store = BlobStore()


def store_blob(data: bytes, content_type: str = "application/octet-stream") -> str:
    """Store a blob and return its content-addressed key."""
    return _default_store.store(data, content_type)


def get_blob(key: str) -> tuple[bytes, str] | None:
    """Retrieve a blob by key. Returns ``(data, content_type)`` or ``None``."""
    return _default_store.get(key)
