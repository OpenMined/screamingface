"""Sibling bindings are visible in an iteration's COLLECTION position (spec §5.3.7 / §6.2).

The body-position twin of this bug lives in `test_iteration_scope.py`: `_lower_iteration`
once discarded enclosing edges for bodies, and a grammar-admitted reference substituted
VERBATIM. The collection slot had the same gap one layer down — `_lower_collection`
lowered with empty edges, so `$gate*(body)` reached the executor as the literal text
`$gate` and failed as "scalar, not an iterable collection", while the identical
reference in body position resolved fine.

WHY this slot matters: a deterministic endpoint returning a 0-or-1-item collection,
iterated by a sibling reference, is the conditional-execution idiom for static DAGs —
an empty collection means the body never executes. That idiom (benchmark gating,
bounded retries) is only expressible if collection references resolve like body
references.

The tests build the pattern where it is renderable and used in anger: gate and
consuming iterate as siblings INSIDE an enclosing iteration body (top-level
intent-bearing groups cannot carry a non-first iteration source — a render-side
constraint unrelated to this fix).
"""

from __future__ import annotations

import json

import pytest

from url4 import RelExpr, Text, expr, iterate, ref, render, src
from url4.peer.server import Request, Url4Node


def _node(calls: list[tuple[str, str]]) -> Url4Node:
    node = Url4Node("collection-scope-test")
    node.data(
        "/cases",
        json.dumps([{"id": 1, "input": "skip this"}, {"id": 2, "input": "run this"}]),
        media_type="application/json",
    )

    @node.endpoint("/gate")
    def gate(request: Request) -> str:
        calls.append(("gate", request.context))
        # Deterministic 0-or-1-item collection keyed on the RESOLVED context — if the
        # sibling reference ever substitutes verbatim, "skip"/"run" never match and
        # the assertion below reveals it.
        return json.dumps([] if "skip" in request.context else [{"go": 1}])

    @node.endpoint("/probe")
    def probe(request: Request) -> str:
        calls.append(("probe", request.intent))
        return json.dumps({"probed": True})

    return node


def _expression() -> str:
    per_case = expr(
        src(
            RelExpr(path="/gate", context="$item.input", intent=Text("g")),
            name="gate",
            weight=0.0,
        ),
        src(
            iterate(
                ref("gate"),
                body=(
                    src(
                        RelExpr(path="/probe", context="$item.go", intent=Text("ran")),
                        name="probed",
                        weight=0.0,
                    ),
                ),
                intent=Text("$probed"),
            ),
            name="outcome",
            weight=0.0,
        ),
        intent=Text("$outcome"),
    )
    rows = iterate(
        "/cases",
        body=(src(per_case, name="checked", weight=0.0),),
        intent=Text("$checked"),
    )
    return render(expr(src(rows, name="rows", weight=0.0), intent=Text("$rows")))


@pytest.mark.asyncio
async def test_collection_references_resolve_and_gate_execution() -> None:
    calls: list[tuple[str, str]] = []
    node = _node(calls)
    try:
        result = await node.evaluate(_expression())
    finally:
        await node.aclose()

    # The gate saw RESOLVED contexts, not the literal `$item.input`.
    assert [context for kind, context in calls if kind == "gate"] == ["skip this", "run this"]
    # Case 1's empty gate executed its body ZERO times; case 2's ran exactly once.
    assert [intent for kind, intent in calls if kind == "probe"] == ["ran"]
    assert json.loads(result.text) == [[], [json.dumps({"probed": True})]] or json.loads(
        result.text
    ) == [[], [{"probed": True}]]


@pytest.mark.asyncio
async def test_an_unknown_collection_name_still_fails_loudly() -> None:
    from url4.core.errors import CollectionError

    calls: list[tuple[str, str]] = []
    node = _node(calls)
    per_case = expr(
        src(
            iterate(
                ref("nowhere"),
                body=(
                    src(
                        RelExpr(path="/probe", context="$item", intent=Text("ran")),
                        name="probed",
                        weight=0.0,
                    ),
                ),
                intent=Text("$probed"),
            ),
            name="outcome",
            weight=0.0,
        ),
        intent=Text("$outcome"),
    )
    rows = iterate(
        "/cases",
        body=(src(per_case, name="checked", weight=0.0),),
        intent=Text("$checked"),
        on_error="fail",
    )
    try:
        with pytest.raises(CollectionError, match="scalar"):
            await node.evaluate(
                render(expr(src(rows, name="rows", weight=0.0), intent=Text("$rows")))
            )
    finally:
        await node.aclose()
