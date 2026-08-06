"""Outer bindings reach an iteration body on the AST path too (spec §6.2 / §8.2).

`test_iteration_scope.py` pins this contract for the TEXT path (`evaluate(text)`). This module
pins the same contract for the PARSE-TREE path (`resolve(build(text))`), which
:class:`~url4.core.nodes.Iteration` names as an invariant in its own docstring.

The two paths collect a source's `$name` references differently. `_slot_from_text` scans the raw
segment, so it sees a reference anywhere in the body. `_slot_from_ast` walks the parse tree — and
`children(Iteration)` yields only ``collection``, because ``body``/``intent``/``reducer`` are
template STRINGS rather than child nodes. So the body's references were invisible to the AST
walk: the enclosing group's slot declared no dependency on them, `_ref_edges` emitted no
``bind:`` edge, and `_lower_iteration` had nothing to wire.

INVARIANT: both paths resolve the same expression to the same text. The failure this guards is
the one the text-path fix already closed — an outer reference substituting VERBATIM, silently,
so an expression that reads correctly yields a confident wrong answer.
"""

from __future__ import annotations

import json

import pytest

from url4 import StaticIOLayer
from url4.core.grammar import parse as grammar_parse
from url4.dag import run

_ROWS = json.dumps([{"id": 1}, {"id": 2}])
_INNER = json.dumps(["X", "Y"])


def _io() -> StaticIOLayer:
    """A world whose `/const` route returns a fixed value, so a resolved reference is visible."""
    return StaticIOLayer(
        fetch_map={"/rows": _ROWS, "/inner": _INNER},
        routes={"/const": lambda context, intent: "OUTER-VALUE"},
    )


async def _ast(expr: str) -> str:
    """Resolve through the PARSE-TREE path — `compile_expression` on a parsed node."""
    return await run(grammar_parse(expr), _io())


async def _text(expr: str) -> str:
    """Resolve through the TEXT path — the same expression as a string."""
    return await run(expr, _io())


# --- the core contract, on the AST path -----------------------------------------


@pytest.mark.asyncio
async def test_the_ast_path_resolves_an_outer_binding_inside_an_iteration_body() -> None:
    result = await _ast("(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$ans)!'row')!'out'")

    assert "OUTER-VALUE" in result
    assert "$ans" not in result


@pytest.mark.asyncio
async def test_the_ast_path_resolves_an_outer_binding_inside_the_per_row_intent() -> None:
    """The per-row intent is a substituted template, so a reference there must resolve too."""
    result = await _ast("(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$item.id)!'saw $ans')!'o'")

    assert "OUTER-VALUE" in result
    assert "$ans" not in result


@pytest.mark.asyncio
async def test_the_ast_path_resolves_an_outer_binding_in_a_NESTED_iteration_body() -> None:
    """Two levels deep — the shape a per-criterion benchmark protocol needs."""
    result = await _ast(
        "(ans:1.0:/const('x')!'c', r:1.0:/rows*(inner:1.0:/inner*(a:1.0:$ans)!'i')!'o')!'out'"
    )

    assert "OUTER-VALUE" in result
    assert "$ans" not in result


# --- the parity invariant -------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expr",
    [
        "(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$ans)!'row')!'out'",
        "(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$item.id)!'saw $ans')!'o'",
        "(r:1.0:/rows*(a:1.0:$item.id)!'row')!'out'",
    ],
)
async def test_the_two_paths_agree(expr: str) -> None:
    """INVARIANT: `evaluate(text) == resolve(build(text))` — Iteration's own docstring.

    Asserted on the RESOLVED STRING rather than on graph structure: the two paths build
    legitimately different node shapes, and it is the observable result that must not diverge.
    """
    assert await _text(expr) == await _ast(expr)


# --- what must NOT change -------------------------------------------------------


@pytest.mark.asyncio
async def test_the_ast_path_keeps_item_shadowing_the_row() -> None:
    """INVARIANT: `$item` is reserved per §5.3.4 and keeps shadowing on this path too.

    Collecting the body's references must not wire an enclosing binding NAMED `item` over the
    row — the exclusion `_body_ref_edges` applies has to apply to the AST walk as well, or the
    two paths disagree about which names an iteration rebinds for itself.
    """
    result = await _ast("(item:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$item.id)!'row')!'out'")
    rows = result[result.index("r: ") :]

    # The rows carry the ROW's id, never the enclosing binding that happens to be named `item`.
    assert "1" in rows
    assert "2" in rows
    assert "OUTER-VALUE" not in rows


@pytest.mark.asyncio
async def test_the_ast_path_leaves_an_undeclared_reference_verbatim() -> None:
    """Unchanged behaviour for a genuinely unbound name — only DECLARED siblings are wired."""
    result = await _ast("(r:1.0:/rows*(a:1.0:$nope)!'row')!'out'")

    assert "$nope" in result


@pytest.mark.asyncio
async def test_an_unreferenced_body_gains_no_edge_on_the_ast_path() -> None:
    """A body that references nothing keeps its previous concurrency — no new dependency."""
    result = await _ast("(ans:1.0:/const('x')!'c', r:1.0:/rows*(a:1.0:$item.id)!'row')!'out'")

    assert "1" in result
    assert "2" in result
