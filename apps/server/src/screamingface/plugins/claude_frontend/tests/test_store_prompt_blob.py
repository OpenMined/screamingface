"""Regression tests for _store_prompt_blob — covers the data-store 404 case.

When the claude-frontend proxy resolves a `$prompt` url4 expression it
stores the user text as a blob via :func:`_store_prompt_blob`. There are
two paths:

1. In-process: write to ``app.state.blob_store`` directly.
2. HTTP: POST to ``{backend_url}/data`` (data-store plugin's route).

The HTTP path is only correct when ``backend_url`` actually points at a
running SF with the data-store plugin. If ``backend_url`` is stale (e.g.
SF auto-incremented its port due to a collision and ``backend_url`` was
captured before the increment) the POST hits whatever else binds the
configured port and returns 404. This was the
``Resolution failed for spec 'anthropic-cookbook'`` bug.

The fix: prefer the in-process path whenever ``app.state.blob_store``
is available, regardless of ``backend_url``. These tests pin that
behavior so the regression can't sneak back.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from screamingface.plugins.claude_frontend._url4_context import _store_prompt_blob
from screamingface.plugins.data_store.storage import BlobStore


class _NullSpan:
    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _NullTracer:
    @contextmanager
    def start_client_span(self, _name: str) -> Any:
        yield _NullSpan()

    def set_attrs(self, _attrs: dict[str, Any]) -> None:
        return None


def _app_with_blob_store() -> Any:
    return SimpleNamespace(state=SimpleNamespace(blob_store=BlobStore()))


@pytest.mark.anyio
async def test_inprocess_path_used_when_blob_store_available() -> None:
    """With an app that has a BlobStore, no HTTP call should happen."""
    app = _app_with_blob_store()
    key = await _store_prompt_blob("hello world", app=app, backend_url=None, tracer=_NullTracer())
    assert isinstance(key, str)
    assert app.state.blob_store.get(key) == (b"hello world", "text/plain; charset=utf-8")


@pytest.mark.anyio
async def test_inprocess_preferred_even_when_backend_url_set() -> None:
    """The historical bug: backend_url set + stale (e.g. 8000 when SF moved
    to 8001) caused HTTP path to 404. We now prefer in-process whenever the
    app has a BlobStore, so a misconfigured backend_url doesn't break the
    flow when both are available."""
    app = _app_with_blob_store()
    # If the HTTP path were taken we'd get a connection error trying to
    # reach a non-existent server here. The in-process path bypasses it.
    key = await _store_prompt_blob(
        "hello",
        app=app,
        backend_url="http://127.0.0.1:1/garbage",  # nothing here, would 404
        tracer=_NullTracer(),
    )
    assert isinstance(key, str)
    assert app.state.blob_store.get(key) == (b"hello", "text/plain; charset=utf-8")


@pytest.mark.anyio
async def test_http_path_used_when_no_inprocess_app() -> None:
    """If the proxy is running OUT-of-process (no app.state.blob_store
    accessible), the HTTP fallback is the only option. Stub out the
    network with httpx.MockTransport."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["body"] = req.read().decode()
        return httpx.Response(200, json={"key": "deadbeef", "url": "/data/deadbeef"})

    transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient to inject our transport via context manager
    import screamingface.plugins.claude_frontend._url4_context as mod

    real_client_cls = mod.httpx.AsyncClient

    class _Client(real_client_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    mod.httpx.AsyncClient = _Client  # type: ignore[misc]
    try:
        # No app -> in-process unavailable -> HTTP path runs
        key = await _store_prompt_blob(
            "abc",
            app=None,
            backend_url="http://gateway",
            tracer=_NullTracer(),
        )
    finally:
        mod.httpx.AsyncClient = real_client_cls  # type: ignore[misc]

    assert key == "deadbeef"
    assert captured["url"] == "http://gateway/data"
    assert captured["method"] == "POST"
    assert captured["body"] == "abc"


@pytest.mark.anyio
async def test_raises_when_no_app_and_no_backend_url() -> None:
    """No app and no backend_url is a programming error — raise loudly."""
    with pytest.raises(RuntimeError, match="requires either"):
        await _store_prompt_blob("x", app=None, backend_url=None, tracer=_NullTracer())
