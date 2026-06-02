"""Tests for bounded concurrency and on_error=collect in collection iteration.

SF-34 Phase 3.1/2.6 — verifies that ;foreach.concurrency=N caps in-flight
coroutines and ;foreach.on_error=collect turns per-row exceptions into
structured error elements rather than propagating them.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.tests.test_ensemble import _make_app


def _fake_resolve_returning(content: str, *, collection_source: str = "DATA"):
    """Return a fake resolve_str that returns ``content`` when called with
    ``collection_source``, and delegates to the real implementation for all
    other contexts (e.g. per-item backend-call expressions like ``(/track(1))``).
    """
    from screamingface.plugins.url4_executor import url4_resolve as _url4_resolve

    _real_resolve_str = _url4_resolve.resolve_str

    async def _fake(context, app, env=None):
        if context == collection_source:
            return content
        return await _real_resolve_str(context, app, env)

    return _fake


@pytest.mark.asyncio
async def test_concurrency_cap_limits_in_flight(monkeypatch):
    state = {"now": 0, "max": 0}

    class _CountingPlugin:
        name = "track"
        backend_call_paths = ["/track"]

        async def handle_backend_call(self, intent, *, sources="", app, env=None):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.02)
            state["now"] -= 1
            return f"ok-{sources}"

    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning("[1, 2, 3, 4, 5, 6]"),
    )
    interp = EnsembleInterpreter(app=_make_app(_CountingPlugin()))  # pyright: ignore[reportArgumentType]
    await interp.evaluate("DATA*(/track($item)) ;foreach.concurrency=2")
    assert state["max"] == 2  # 6 rows, cap 2 → never more than 2 in flight


@pytest.mark.asyncio
async def test_unbounded_without_directive(monkeypatch):
    state = {"now": 0, "max": 0}

    class _CountingPlugin:
        name = "track"
        backend_call_paths = ["/track"]

        async def handle_backend_call(self, intent, *, sources="", app, env=None):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.02)
            state["now"] -= 1
            return "ok"

    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning("[1, 2, 3, 4]"),
    )
    interp = EnsembleInterpreter(app=_make_app(_CountingPlugin()))  # pyright: ignore[reportArgumentType]
    await interp.evaluate("DATA*(/track($item))")  # no directive → all 4 concurrent
    assert state["max"] == 4


@pytest.mark.asyncio
async def test_on_error_collect_yields_error_element(monkeypatch):
    class _FailOnTwoPlugin:
        name = "x"
        backend_call_paths = ["/x"]

        async def handle_backend_call(self, intent, *, sources="", app, env=None):
            if sources == "2":
                raise RuntimeError("boom")
            return f"ok-{sources}"

    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning("[1, 2, 3]"),
    )
    interp = EnsembleInterpreter(app=_make_app(_FailOnTwoPlugin()))  # pyright: ignore[reportArgumentType]
    result = await interp.evaluate("DATA*(/x($item)) ;foreach.on_error=collect")
    lines = result.split("\n")
    error_elements = [json.loads(line) for line in lines if '"error"' in line]
    assert len(error_elements) == 1  # exactly row 2 collected as an error element
    assert error_elements[0]["error"]["kind"] == "RuntimeError"
    assert any("ok-1" in line for line in lines)
    assert any("ok-3" in line for line in lines)


@pytest.mark.asyncio
async def test_default_abort_propagates_error(monkeypatch):
    class _FailOnTwoPlugin:
        name = "x"
        backend_call_paths = ["/x"]

        async def handle_backend_call(self, intent, *, sources="", app, env=None):
            if sources == "2":
                raise RuntimeError("boom")
            return f"ok-{sources}"

    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning("[1, 2, 3]"),
    )
    interp = EnsembleInterpreter(app=_make_app(_FailOnTwoPlugin()))  # pyright: ignore[reportArgumentType]
    with pytest.raises(RuntimeError):
        await interp.evaluate("DATA*(/x($item))")  # default abort → first error propagates
