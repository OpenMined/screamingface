"""Regression tests for _resolve_expression — covers the /ensemble 401 + /data 404.

When the claude-frontend proxy resolves a ``$prompt`` url4 expression it
evaluates the substituted expression via :func:`_resolve_expression`. The blob
holding the user's prompt was written by ``_store_prompt_blob`` either:

1. in-process (when this ``app`` owns ``app.state.blob_store``), or
2. on the main server via HTTP ``POST /data`` (when it doesn't).

Resolution must read the blob back from the SAME locus, so ``_resolve_expression``
mirrors ``_store_prompt_blob``'s guard:

- in-process when ``app.state.blob_store`` exists, else
- HTTP ``GET {backend_url}/ensemble`` with the ``X-SF-Desktop-Secret`` header
  (SF-174 guards ``/ensemble``; the per-session process reads the same shared
  secret via ``SF_DESKTOP_SECRET_FILE``).

History: SF-230 resolved in-process whenever ``app is not None``. Because the
proxy runs as a separate per-session app whose ``app`` lacks ``blob_store``, the
blob lived on the main server but in-process resolution read the proxy app ->
404 on ``/data/{key}``. These tests pin the locus-matched behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import screamingface.plugins.claude_frontend._url4_context as mod
import screamingface.plugins.url4_executor.interpreter as interpreter_mod
from screamingface.plugins.claude_frontend._url4_context import _resolve_expression


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


class _FakeInterpreter:
    """Stands in for Url4Interpreter; records the app and returns a fixed text."""

    last_app: Any = None

    def __init__(self, app: Any = None) -> None:
        _FakeInterpreter.last_app = app

    async def evaluate(self, expr: str) -> str:
        return f"inprocess:{expr}"


def _app_with_blob_store() -> Any:
    return SimpleNamespace(state=SimpleNamespace(blob_store=object()))


def _app_without_blob_store() -> Any:
    return SimpleNamespace(state=SimpleNamespace())


@contextmanager
def _mock_ensemble_transport(handler):  # type: ignore[no-untyped-def]
    """Route _url4_context's httpx.AsyncClient through a MockTransport."""
    transport = httpx.MockTransport(handler)
    real_client_cls = mod.httpx.AsyncClient

    class _Client(real_client_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    mod.httpx.AsyncClient = _Client  # type: ignore[misc]
    try:
        yield
    finally:
        mod.httpx.AsyncClient = real_client_cls  # type: ignore[misc]


@pytest.mark.anyio
async def test_inprocess_used_when_app_owns_blob_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """When this app owns the blob store, resolve in-process (where the blob is)."""
    monkeypatch.setattr(interpreter_mod, "Url4Interpreter", _FakeInterpreter)
    app = _app_with_blob_store()

    # backend_url is set but must be ignored — the blob lives in-process here.
    result = await _resolve_expression(
        "(https://x)!intent",
        app=app,
        backend_url="http://127.0.0.1:1/garbage",
        tracer=_NullTracer(),
    )

    assert result == "inprocess:(https://x)!intent"
    assert _FakeInterpreter.last_app is app


@pytest.mark.anyio
async def test_http_with_secret_when_app_lacks_blob_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """No local blob store -> blob is on the main server; resolve via HTTP /ensemble
    and carry the desktop secret so SF-174's guard accepts it."""
    monkeypatch.setattr(mod, "configured_desktop_secret", lambda: "s3cr3t")
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["secret"] = req.headers.get(mod.DESKTOP_SECRET_HEADER)
        return httpx.Response(200, text="ensemble-result")

    with _mock_ensemble_transport(handler):
        result = await _resolve_expression(
            "(https://x)!/data/abc",
            app=_app_without_blob_store(),
            backend_url="http://gateway",
            tracer=_NullTracer(),
        )

    assert result == "ensemble-result"
    assert captured["url"].startswith("http://gateway/ensemble?q=")
    assert captured["secret"] == "s3cr3t"


@pytest.mark.anyio
async def test_http_no_secret_header_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no desktop secret is configured, no header is sent (guard is a no-op then)."""
    monkeypatch.setattr(mod, "configured_desktop_secret", lambda: None)
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["secret"] = req.headers.get(mod.DESKTOP_SECRET_HEADER)
        return httpx.Response(200, text="ok")

    with _mock_ensemble_transport(handler):
        result = await _resolve_expression(
            "(https://x)", app=None, backend_url="http://gateway", tracer=_NullTracer()
        )

    assert result == "ok"
    assert captured["secret"] is None


@pytest.mark.anyio
async def test_raises_when_no_blob_store_app_and_no_backend_url() -> None:
    """No in-process blob store and no backend_url is a programming error."""
    with pytest.raises(RuntimeError, match="requires either"):
        await _resolve_expression(
            "x", app=_app_without_blob_store(), backend_url=None, tracer=_NullTracer()
        )
