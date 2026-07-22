"""Spec §5.3.12 — source expansion: `*source` prefix and `;expand` annotation."""

from __future__ import annotations

import pytest

from url4 import StaticIOLayer
from url4.core.context import Context
from url4.core.errors import Url4Error
from url4.core.grammar import parse
from url4.core.nodes import Url
from url4.dag import run

# --- parse level -----------------------------------------------------------------


def test_prefix_form_marks_expansion() -> None:
    # §5.3.12.2 prefix form
    from url4.core.nodes import Source

    node = parse("*https://thepost.com/feed")
    assert isinstance(node, Source)
    assert node.expand is True
    assert node.value == Url("https://thepost.com/feed")


def test_annotation_form_marks_expansion() -> None:
    # §5.3.12.2 annotation form
    from url4.core.nodes import Source

    node = parse("https://thepost.com/feed;expand")
    assert isinstance(node, Source)
    assert node.expand is True
    assert node.value == Url("https://thepost.com/feed")


def test_prefix_and_annotation_forms_equivalent_expansion() -> None:
    # §5.3.12.2 — "Both are semantically identical"
    from url4.core.nodes import Source

    prefix = parse("*https://thepost.com/feed")
    annotated = parse("https://thepost.com/feed;expand")
    assert isinstance(prefix, Source) and isinstance(annotated, Source)
    assert prefix.expand is annotated.expand is True
    assert prefix.value == annotated.value


def test_prefix_form_with_name_and_weight() -> None:
    # §5.3.12.2 — "*articles:0.5:https://thepost.com/feed"
    from url4.core.nodes import Source

    node = parse("*articles:0.5:https://thepost.com/feed")
    assert isinstance(node, Source)
    assert node.expand is True
    assert node.name == "articles"
    assert node.weight == 0.5


def test_prefix_position_distinct_from_iteration() -> None:
    # §5.3.12.3 — source-initial '*' is expansion; mid-value '*(' is iteration
    from url4.core.nodes import Iteration, Source

    expansion = parse("*https://thepost.com/feed")
    iteration = parse("https://data.com/records*(x)!'go'")
    assert isinstance(expansion, Source) and expansion.expand
    assert isinstance(iteration, Iteration)


# --- runtime ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expansion_splices_elements_into_source_list() -> None:
    # §5.3.12.4 — each element becomes an independent source at its position
    captured: dict[str, str] = {}

    async def capture(sources: str, intent: str | None, scope: Context) -> str:
        captured["sources"] = sources
        return "done"

    io = StaticIOLayer({"https://coll": '["A", "B"]', "https://o": "O"})
    await run("(*https://coll, https://o)!'merge'", io, process=capture)
    assert captured["sources"] == "A\nB\nO"


@pytest.mark.asyncio
async def test_expansion_renumbers_positional_references() -> None:
    # §5.3.12.4 — source positions renumbered after expansion
    io = StaticIOLayer({"https://coll": '["A", "B"]', "https://o": "O"})
    result = await run("(*https://coll, https://o)!'$1|$2|$3'", io)
    assert "A|B|O" in result


@pytest.mark.asyncio
async def test_annotation_form_runtime_equivalent() -> None:
    # §5.3.12.2 — `;expand` behaves identically to the prefix form
    io = StaticIOLayer({"https://coll": '["A", "B"]', "https://o": "O"})
    result = await run("(https://coll;expand, https://o)!'$1|$2|$3'", io)
    assert "A|B|O" in result


@pytest.mark.asyncio
async def test_expansion_not_iterable_error() -> None:
    # §5.3.12.4 — non-iterable resolved value → expansion_not_iterable
    io = StaticIOLayer({"https://coll": "a single scalar value"})
    with pytest.raises(Url4Error) as exc_info:
        await run("(*https://coll, other)!'merge'", io)
    assert exc_info.value.code == "expansion_not_iterable"
