"""Outer bindings are visible inside an iteration body (spec §6.2 / §8.2).

The grammar admits `$name` anywhere a `value` is admitted, including inside an iteration's
per-row expression — `item-ref` reserves the NAME `$item` within iteration bodies, it does not
make it the only name in scope. Before this, `_lower_iteration` discarded the enclosing group's
edges, so a reference the grammar allows resolved to nothing and substituted VERBATIM: the
downstream leaf received the literal characters `$ans`.

That failure was silent in both field-path modes, which is what makes it worth a regression
suite: an expression that reads correctly produced a prompt containing `$ans` and a confident,
wrong answer.
"""

from __future__ import annotations

import json

import pytest

from url4 import StaticIOLayer, evaluate_sync
from url4.peer.server import Request, Url4Node

_ROWS = json.dumps([{"id": 1}, {"id": 2}])


def _node(**endpoints):
    """A node whose `/echo` returns its context, so a resolved value is directly observable."""
    node = Url4Node("scope-test", default_processor="/echo")
    node.data("/rows", _ROWS, media_type="application/json")

    @node.endpoint("/echo")
    def echo(request: Request) -> str:
        return request.context

    @node.endpoint("/const")
    def const(request: Request) -> str:
        return "OUTER-VALUE"

    return node


async def _eval(expr: str) -> str:
    node = _node()
    try:
        return (await node.evaluate(expr)).text
    finally:
        await node.aclose()


# --- the core contract ----------------------------------------------------------


@pytest.mark.asyncio
async def test_an_outer_binding_resolves_inside_an_iteration_body() -> None:
    result = await _eval("(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$ans)!'row')!'out'")

    assert "OUTER-VALUE" in result
    assert "$ans" not in result


@pytest.mark.asyncio
async def test_an_outer_binding_resolves_inside_the_per_row_intent() -> None:
    """The intent is a substituted template, so a reference there must resolve too."""
    result = await _eval("(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$item.id)!'saw $ans')!'o'")

    assert "OUTER-VALUE" in result
    assert "$ans" not in result


@pytest.mark.asyncio
async def test_an_outer_binding_resolves_inside_a_NESTED_iteration_body() -> None:
    """Two levels deep — the shape a per-criterion benchmark protocol needs.

    The answer is computed ONCE in the outer scope and read by every inner row; recomputing it
    per inner row would multiply model cost by the inner collection's length.
    """
    result = await _eval(
        "(ans:1.0:/const('x')!'c', r:1.0:/rows*(inner:1.0:/rows*(a:1.0:$ans)!'i')!'o')!'out'"
    )

    assert "OUTER-VALUE" in result
    assert "$ans" not in result


# --- what must NOT change -------------------------------------------------------


@pytest.mark.asyncio
async def test_item_still_refers_to_the_row_not_an_outer_binding() -> None:
    """INVARIANT: `$item` is reserved per §5.3.4 and must keep shadowing at every level.

    Wiring outer references must not let an outer `item` binding capture the row — the row is
    bound under a reserved NUL-prefixed key precisely to stay out of the `$name` namespace.
    """
    result = await _eval("(r:1.0:/rows*(a:1.0:$item.id)!'row')!'out'")

    assert "1" in result
    assert "2" in result


@pytest.mark.asyncio
async def test_the_inner_item_wins_over_the_outer_item_in_a_nested_iteration() -> None:
    node = _node()
    node.data("/inner", json.dumps(["X", "Y"]), media_type="application/json")
    try:
        result = (
            await node.evaluate("(r:1.0:/rows*(i:1.0:/inner*(a:1.0:$item)!'in')!'out')!'o'")
        ).text
    finally:
        await node.aclose()

    # The innermost row values, not the outer {"id": …} objects.
    assert "X" in result
    assert "Y" in result


@pytest.mark.asyncio
async def test_an_unreferenced_binding_adds_no_edge() -> None:
    """A body that references nothing must behave exactly as before — no new dependency, so no
    accidental serialisation of an iteration behind an unrelated sibling."""
    result = await _eval("(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$item.id)!'row')!'out'")

    assert "1" in result


@pytest.mark.asyncio
async def test_a_reference_to_an_undeclared_name_still_substitutes_verbatim() -> None:
    """Unchanged behaviour for a genuinely unbound name — this fix wires DECLARED siblings only,
    it does not change what an unknown reference does."""
    result = await _eval("(r:1.0:/rows*(a:1.0:$nope)!'row')!'out'")

    assert "$nope" in result


def test_a_static_world_iteration_still_resolves_offline() -> None:
    """The engine core stays I/O-inverted: no endpoint, no network, still substitutes."""
    io = StaticIOLayer(fetch_map={"/c": json.dumps(["a", "b"])})

    assert evaluate_sync("(/c*(x:1.0:$item)!'r')!'o'", io).text is not None
