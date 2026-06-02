"""Integration test for the per-row scoring body in the v1 scored query.

SF-34 Phase 1.5 — verifies that a binding (consensus) in a per-row body
does NOT pollute the per-row result fed to the collection reducer.
"""

from __future__ import annotations

import json

import pytest

from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app


def _fake_resolve_returning(content: str, *, collection_source: str = "D"):
    """Return a fake resolve_str that returns ``content`` when called with
    ``collection_source``, and delegates to the real implementation for all
    other contexts (e.g. per-item backend-call expressions).
    """
    from screamingface.plugins.url4_executor import url4_resolve as _url4_resolve

    _real_resolve_str = _url4_resolve.resolve_str

    async def _fake(context, app, env=None):
        if context == collection_source:
            return content
        return await _real_resolve_str(context, app, env)

    return _fake


@pytest.mark.asyncio
async def test_per_row_consensus_binding_feeds_check_correct(monkeypatch):
    # claude answers the row's question; check_correct receives expected + consensus.
    class _ClaudePlugin:
        name = "claude"
        backend_call_paths = ["/claude"]

        async def handle_backend_call(self, intent, *, sources="", app, env=None):
            # `sources` is the substituted question text (packed_context)
            return "Paris" if "France" in sources else "London"

    py = _FakeDispatchPlugin(
        name="python-runner",
        paths=["/python"],
        responses=['{"correct": true, "predicted": "Paris"}'] * 8,
    )
    app = _make_app(_ClaudePlugin(), py)  # pyright: ignore[reportArgumentType]

    dataset = json.dumps(
        [
            {"question": "capital of France?", "expected_answer": "Paris"},
            {"question": "capital of UK?", "expected_answer": "London"},
        ]
    )

    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning(dataset, collection_source="D"),
    )

    interp = EnsembleInterpreter(app=app)
    body = (
        "consensus=/claude($item.question)!'answer', "
        "/python(/data/code/check_correct.py)!"
        '{"question":"$item.question","expected":"$item.expected_answer",'
        '"correct_answer":"$item.expected_answer","consensus":"$consensus"}'
    )
    expr = f"(D*({body}) ;foreach.concurrency=2)!/python(/data/code/calculate_accuracy.py)"
    await interp.evaluate(expr)

    # (a) check_correct got fully-substituted, valid multi-key JSON payloads
    check_calls = [c for c in py.calls if "check_correct" in c[1]]
    assert len(check_calls) == 2
    for intent, _sources, _app in check_calls:
        assert "$" not in intent  # all $item.* and $consensus resolved
        payload = json.loads(intent)  # valid JSON (json_blob parsed)
        assert payload["expected"] in ("Paris", "London")
        assert payload["consensus"] == payload["expected"]  # claude returned the row's answer

    # (b) the collection reducer received a CLEAN array of per-row verdicts —
    #     NOT polluted with the consensus string (this is the _resolve_list fix)
    reducer_calls = [c for c in py.calls if "calculate_accuracy" in c[1]]
    assert len(reducer_calls) == 1
    arr = json.loads(reducer_calls[0][0])
    assert arr == [{"correct": True, "predicted": "Paris"}, {"correct": True, "predicted": "Paris"}]
