"""Sibling bindings remain visible in an iteration collection position."""

from __future__ import annotations

import json

import pytest

from url4 import RelExpr, Text, expr, iterate, ref, render, src
from url4.core.errors import CollectionError
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
        return json.dumps([] if "skip" in request.context else [{"go": 1}])

    @node.endpoint("/probe")
    def probe(request: Request) -> str:
        calls.append(("probe", request.intent))
        return json.dumps({"probed": True})

    return node


def _expression(collection: str = "gate") -> str:
    per_case = expr(
        src(
            RelExpr(path="/gate", context="$item.input", intent=Text("g")),
            name="gate",
            weight=0.0,
        ),
        src(
            iterate(
                ref(collection),
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
        on_error="fail",
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

    assert [context for kind, context in calls if kind == "gate"] == ["skip this", "run this"]
    assert [intent for kind, intent in calls if kind == "probe"] == ["ran"]
    assert json.loads(result.text) in (
        [[], [json.dumps({"probed": True})]],
        [[], [{"probed": True}]],
    )


@pytest.mark.asyncio
async def test_an_unknown_collection_name_still_fails_loudly() -> None:
    calls: list[tuple[str, str]] = []
    node = _node(calls)
    try:
        with pytest.raises(CollectionError, match="scalar"):
            await node.evaluate(_expression("nowhere"))
    finally:
        await node.aclose()
