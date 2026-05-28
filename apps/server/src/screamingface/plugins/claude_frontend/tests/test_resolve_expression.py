"""Regression tests for _resolve_expression — covers the /ensemble 401 self-loop.

When the claude-frontend proxy resolves a ``$prompt`` url4 expression it
evaluates the substituted expression via :func:`_resolve_expression`. Two
paths:

1. In-process: ``Url4Interpreter(app=app).evaluate(...)`` (same interpreter
   ``GET /ensemble`` uses).
2. HTTP: GET ``{backend_url}/ensemble`` (only correct out-of-process).

The HTTP path self-loops back into the proxy's own SF. Since SF-174 guarded
``/ensemble`` with the desktop secret, that self-call returns 401 when
``SF_DESKTOP_SECRET`` is set (the desktop always sets it). The fix: prefer the
in-process path whenever ``app`` is available — mirroring ``_store_prompt_blob``.
These tests pin that behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

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


@pytest.mark.anyio
async def test_inprocess_path_used_when_app_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """With an app, evaluation goes through the in-process interpreter, not HTTP."""
    monkeypatch.setattr(interpreter_mod, "Url4Interpreter", _FakeInterpreter)
    app = SimpleNamespace(state=SimpleNamespace())

    result = await _resolve_expression(
        "(https://x)!intent", app=app, backend_url=None, tracer=_NullTracer()
    )

    assert result == "inprocess:(https://x)!intent"
    assert _FakeInterpreter.last_app is app


@pytest.mark.anyio
async def test_inprocess_preferred_even_when_backend_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug: backend_url set + /ensemble now secret-protected -> 401 on the
    HTTP self-loop. We prefer in-process whenever an app is present, so a set
    backend_url doesn't drag us into the self-call."""
    monkeypatch.setattr(interpreter_mod, "Url4Interpreter", _FakeInterpreter)
    app = SimpleNamespace(state=SimpleNamespace())

    # If the HTTP path were taken it would try to reach this dead address.
    result = await _resolve_expression(
        "(https://x)!intent",
        app=app,
        backend_url="http://127.0.0.1:1/garbage",
        tracer=_NullTracer(),
    )

    assert result == "inprocess:(https://x)!intent"


@pytest.mark.anyio
async def test_http_path_used_when_no_inprocess_app() -> None:
    """Out-of-process (no app): the HTTP /ensemble fallback is the only option."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        return httpx.Response(200, text="ensemble-result")

    transport = httpx.MockTransport(handler)

    import screamingface.plugins.claude_frontend._url4_context as mod

    real_client_cls = mod.httpx.AsyncClient

    class _Client(real_client_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    mod.httpx.AsyncClient = _Client  # type: ignore[misc]
    try:
        result = await _resolve_expression(
            "(https://x)", app=None, backend_url="http://gateway", tracer=_NullTracer()
        )
    finally:
        mod.httpx.AsyncClient = real_client_cls  # type: ignore[misc]

    assert result == "ensemble-result"
    assert captured["url"] == "http://gateway/ensemble?q=%28https%3A%2F%2Fx%29"
    assert captured["method"] == "GET"


@pytest.mark.anyio
async def test_raises_when_no_app_and_no_backend_url() -> None:
    """No app and no backend_url is a programming error — raise loudly."""
    with pytest.raises(RuntimeError, match="requires either"):
        await _resolve_expression("x", app=None, backend_url=None, tracer=_NullTracer())
