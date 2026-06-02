"""Tests for the collection-level reducer over a per-row result array.

SF-34 Phase 3.1/3.4 — verifies the NEW evaluation shape::

    (DATA*(BODY) ;foreach...)!/python(reducer)

The parenthesized collection-iteration's per-row results are collected into a
JSON array and fed to a single collection-level reducer node.
"""

from __future__ import annotations

import json

import pytest

from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.tests.test_ensemble import (
    _FakeDispatchPlugin,
    _make_app,
)


def _fake_resolve_returning(content: str, *, collection_source: str = "D"):
    """Return a fake resolve_str that returns ``content`` when called with
    ``collection_source``, delegating to the real implementation otherwise.
    """
    from screamingface.plugins.url4_executor import url4_resolve as _url4_resolve

    _real_resolve_str = _url4_resolve.resolve_str

    async def _fake(context, app, env=None):
        if context == collection_source:
            return content
        return await _real_resolve_str(context, app, env)

    return _fake


@pytest.mark.asyncio
async def test_collection_reducer_receives_json_array(monkeypatch):
    # Same fake plugin handles BOTH the per-row /python(c.py) and the reducer
    # /python(agg.py). Per-row calls return "row-ok"; reducer must receive a
    # JSON array of the 3 per-row results.
    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=["row-ok"] * 4)
    app = _make_app(py)
    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning("[1, 2, 3]"),
    )
    interp = EnsembleInterpreter(app=app)  # pyright: ignore[reportArgumentType]
    expr = '(D*(/python(/data/code/c.py)!{"row":"$item"}))!/python(/data/code/agg.py)'
    await interp.evaluate(expr)
    # the LAST /python call is the reducer; its intent (calls[-1][0]) is the JSON array
    reducer_payload = json.loads(py.calls[-1][0])
    assert isinstance(reducer_payload, list)
    assert len(reducer_payload) == 3
    # and the reducer's sources is the agg script
    assert py.calls[-1][1] == "/data/code/agg.py"


@pytest.mark.asyncio
async def test_reducer_array_preserves_per_row_json(monkeypatch):
    # If per-row results are JSON objects, the reducer array contains parsed objects.
    py = _FakeDispatchPlugin(
        name="python-runner",
        paths=["/python"],
        responses=['{"correct": true}', '{"correct": false}', '{"correct": true}', "IGNORED"],
    )
    app = _make_app(py)
    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning("[1, 2, 3]"),
    )
    interp = EnsembleInterpreter(app=app)  # pyright: ignore[reportArgumentType]
    expr = '(D*(/python(/data/code/c.py)!{"row":"$item"}))!/python(/data/code/agg.py)'
    await interp.evaluate(expr)
    arr = json.loads(py.calls[-1][0])
    assert arr == [{"correct": True}, {"correct": False}, {"correct": True}]
