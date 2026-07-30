"""One lazily constructed synchronous module-level Client."""

from __future__ import annotations

import os
from threading import Lock

from screamingface.client import DEFAULT_ENGINE_URL, Client

_client: Client | None = None
_lock = Lock()


def default_client() -> Client:
    """Return the process-wide Client, constructing it on first use."""

    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is None:
            _client = Client(
                engine_url=os.environ.get("SCREAMINGFACE_ENGINE_URL", DEFAULT_ENGINE_URL)
            )
    return _client


__all__: list[str] = []
