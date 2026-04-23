"""Shared httpx client factory for backend plugins.

Every concrete ``Backend`` subclass needs an ``httpx.AsyncClient`` with
the same SSL context and timeout shape (10s connect, long read, 10s
write/pool). Defining that once here keeps the four direct-API
backends aligned on TLS behavior and lets us tune the timeouts
globally.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable

import certifi
import httpx

__all__ = ["default_http_factory", "make_http_factory"]


def default_http_factory() -> httpx.AsyncClient:
    """Build an AsyncClient with the canonical timeout + TLS settings."""
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
        verify=ssl_ctx,
    )


def make_http_factory(
    *,
    connect_timeout: float = 10.0,
    read_timeout: float = 300.0,
    write_timeout: float = 10.0,
    pool_timeout: float = 10.0,
) -> Callable[[], httpx.AsyncClient]:
    """Factory of factories — for backends that need non-default timeouts.

    Most backends should use :func:`default_http_factory` directly.
    Use this only when a provider genuinely needs different numbers
    (e.g. a local Ollama server that should fail fast).
    """
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=write_timeout,
                pool=pool_timeout,
            ),
            verify=ssl_ctx,
        )

    return factory
