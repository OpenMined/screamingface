"""ABNF conformance — source contribution semantics (OME-534).

The external formal ABNF (owner-adopted 2026-07-21) makes EVERY named source a
contributing source: `annotated-source = [name-part ":"] … data-binding` and
`sugar-source name=value` ("equivalent to name-part : value"). The engine's
former reference-only-Binding exclusion is replaced by:

- name-only sources (both forms) CONTRIBUTE, packed as ``name: value`` lines;
- scalar ``weight 0.0`` marks a source INSTRUMENTAL — resolved and
  ``$name``-referenceable, excluded from the packed context;
- fan-out reduces label name-only calls ``name:`` instead of demoting the
  group to a local merge.
"""

from __future__ import annotations

import pytest

from url4 import StaticIOLayer
from url4.dag import run

pytestmark = pytest.mark.asyncio

# --- local merge (ProcessNode) packing ---------------------------------------


async def test_name_colon_source_contributes_labeled() -> None:
    # INVARIANT: everything the author lists is data the processor sees.
    io = StaticIOLayer({"/doc": "DOC"})
    result = await run("(named: /doc, 'lit')!'REDUCE'", io)
    assert result == "REDUCE\n\nnamed: DOC\nlit"


async def test_name_equals_source_contributes_labeled() -> None:
    # sugar-source name=value ≡ name-part ":" value — both contribute.
    io = StaticIOLayer({"/doc": "DOC"})
    result = await run("(named=/doc, 'lit')!'REDUCE'", io)
    assert result == "REDUCE\n\nnamed: DOC\nlit"


async def test_weighted_named_source_packs_labeled() -> None:
    io = StaticIOLayer({"/doc": "DOC"})
    result = await run("(judged:0.5:/doc, 'lit')!'REDUCE'", io)
    assert result == "REDUCE\n\njudged: DOC\nlit"


async def test_weight_zero_is_instrumental_but_referenceable() -> None:
    # weight 0.0 replaces the old reference-only Binding: excluded from the
    # packed context, still substitutable via $name.
    io = StaticIOLayer({"/hidden": "SECRET"})
    result = await run("(q:0.0:/hidden, 'lit')!'REDUCE $q'", io)
    assert "SECRET" in result.partition("\n\n")[0]  # $q substituted into intent
    assert result.partition("\n\n")[2] == "lit"  # not packed as a source


async def test_unnamed_sources_still_pack_bare() -> None:
    io = StaticIOLayer({"/doc": "DOC"})
    result = await run("(/doc, 'lit')!'REDUCE'", io)
    assert result == "REDUCE\n\nDOC\nlit"


async def test_lazy_group_binding_contributes_labeled() -> None:
    # A deferred name=(group)!intent binding is a source like any other now.
    io = StaticIOLayer({})
    result = await run("(g=('a','b')!'join', 'lit')!'REDUCE'", io)
    head, _, packed = result.partition("\n\n")
    assert head == "REDUCE"
    assert packed.startswith("g: join")
    assert packed.endswith("lit")


# --- fan-out reduce ----------------------------------------------------------


def _judge_io() -> StaticIOLayer:
    async def route(context: str, intent: str) -> str:
        return f"EP[{context}|{intent}]"

    return StaticIOLayer(routes={"/ep": route, "/reduce": route})


async def test_name_only_call_joins_the_fanout_labeled() -> None:
    # The named call is a fan-out member with a `name:` section header — the
    # group must NOT demote to a local merge just because a member is named.
    io = _judge_io()
    result = await run("(named:/ep('a')!'x', /ep('b')!'y')!'merge'", io, processor="/reduce")
    # the reducer route received labeled sections for both responses
    assert "named:" in result
    assert "EP[a|x]" in result
    assert "EP[b|y]" in result
    assert "merge" in result


async def test_weight_zero_call_excluded_from_reducer_input() -> None:
    io = _judge_io()
    result = await run("(h:0.0:/ep('a')!'x', /ep('b')!'y')!'use $h'", io, processor="/reduce")
    # $h substituted into the instruction …
    assert "EP[a|x]" in result
    # … but h's response is not a labeled section of the reducer input
    assert "h (weight=0):" not in result
    assert "h:" not in result.partition("[Instruction]")[0].replace("EP[a|x]", "")


async def test_weighted_fanout_labels_unchanged() -> None:
    # Guard: the existing `name (weight=w):` labeling stays intact.
    io = _judge_io()
    result = await run("(a:0.6:/ep('a')!'x', b:0.4:/ep('b')!'y')!'merge'", io, processor="/reduce")
    assert "a (weight=0.6):" in result
    assert "b (weight=0.4):" in result
