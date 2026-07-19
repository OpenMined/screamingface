"""Process-local configuration for the one effective URL4 engine."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

DEFAULT_ENGINE_URL = "http://127.0.0.1:4404"
_engine_url = DEFAULT_ENGINE_URL


def config(engine: str = DEFAULT_ENGINE_URL) -> None:
    """Set the URL4 engine used by discovery, loading, and later execution.

    Configuration is deliberately network-free. The first operation requiring the
    engine performs the first request.
    """

    global _engine_url
    _engine_url = _normalize_engine_url(engine)


def current_engine_url() -> str:
    """Return the normalized internal engine URL."""

    return _engine_url


def _normalize_engine_url(engine: object) -> str:
    if not isinstance(engine, str) or not engine.strip():
        raise ValueError("engine must be a non-empty HTTP(S) URL")
    parts = urlsplit(engine.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("engine must be an HTTP(S) URL")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("engine must be an HTTP(S) origin without a path, query, or fragment")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
