"""Spec §6.1 / §6.2 / §8.2 — variable references with field paths, mode
strictness, and broadcast (`!*`, `$current`, result shape)."""

from __future__ import annotations

import json

import pytest

from url4 import StaticIOLayer, run
from url4.context import Context
from url4.errors import ScopeError

RECORD = '{"author": {"name": "Ada"}, "tags": ["t1", "t2"], "reviews": [{"text": "Great"}]}'


async def echo_intent(sources: str, intent: str | None, scope: Context) -> str:
    return intent or ""


# --- field paths on ordinary references (§6.2) -----------------------------------


@pytest.mark.asyncio
async def test_named_reference_nested_dot_path() -> None:
    # §6.2 "Field path with dot notation"
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(data=https://x)!'By $data.author.name'", io)
    assert result == "By Ada"


@pytest.mark.asyncio
async def test_named_reference_array_index() -> None:
    # §6.2 "Field path with array indexing"
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(data=https://x)!'First $data.tags[0]'", io)
    assert result == "First t1"


@pytest.mark.asyncio
async def test_named_reference_combined_traversal() -> None:
    # §6.2 "Combined dot and bracket traversal"
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(data=https://x)!'R: $data.reviews[0].text'", io)
    assert result == "R: Great"


@pytest.mark.asyncio
async def test_positional_reference_with_field_path() -> None:
    # §6.2 — field paths apply identically to $N references
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(https://x)!'$1.author.name'", io, process=echo_intent)
    assert result == "Ada"


@pytest.mark.asyncio
async def test_embedded_reference_in_quoted_text_with_brackets() -> None:
    # §8.2.2 — interpolation inside quoted text consumes bracket paths
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(data=https://x)!'The first tag is $data.tags[0] by $data.author.name'", io)
    assert result == "The first tag is t1 by Ada"


# --- error handling by mode (§5.3.4.1) ---------------------------------------------


@pytest.mark.asyncio
async def test_missing_field_lenient_default_substitutes_empty() -> None:
    # §5.3.4.1 — LLM mode: SHOULD substitute empty string (contract #8)
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(data=https://x)!'X $data.missing Y'", io)
    assert result == "X  Y"


@pytest.mark.asyncio
async def test_index_out_of_bounds_lenient_substitutes_empty() -> None:
    # §5.3.4.1 — out-of-bounds is lenient in LLM mode
    io = StaticIOLayer({"https://x": RECORD})
    result = await run("(data=https://x)!'X $data.tags[9] Y'", io)
    assert result == "X  Y"


@pytest.mark.asyncio
async def test_missing_field_strict_mode_raises() -> None:
    # §5.3.4.1 — RDS mode: MUST fail with malformed_source
    io = StaticIOLayer({"https://x": RECORD})
    with pytest.raises(ScopeError) as exc_info:
        await run("(data=https://x)!'X $data.missing Y'", io, strict_fields=True)
    assert exc_info.value.code == "malformed_source"


@pytest.mark.asyncio
async def test_index_on_scalar_strict_mode_raises() -> None:
    # §5.3.4.1 — "Index on scalar" row
    io = StaticIOLayer({"https://x": '{"name": "Alice"}'})
    with pytest.raises(ScopeError):
        await run("(data=https://x)!'$data.name[0]'", io, strict_fields=True)


# --- escapes and unknowns (§6.2) ------------------------------------------------------


@pytest.mark.asyncio
async def test_double_dollar_is_literal() -> None:
    # §6.2 — $$ produces a literal dollar sign
    result = await run("()!it costs $$5", StaticIOLayer())
    assert result == "it costs $5"


@pytest.mark.asyncio
async def test_unknown_reference_left_verbatim() -> None:
    # §6.3 — LLM mode references are advisory; unknown names stay verbatim
    result = await run("()!hello $nobody", StaticIOLayer())
    assert result == "hello $nobody"


@pytest.mark.asyncio
async def test_positional_references_resolve() -> None:
    # §6.2 "Positional references"
    io = StaticIOLayer({"https://x": "X", "https://y": "Y"})
    result = await run("(https://x, https://y)!'first=$1 second=$2'", io, process=echo_intent)
    assert result == "first=X second=Y"


# --- broadcast (§6.1) ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_result_is_json_collection() -> None:
    # §6.1.4 — ordered collection of per-source results (contract #7)
    io = StaticIOLayer({"https://x": "A", "https://y": "B"})
    result = await run("(https://x, https://y)!*'claims'", io, process=echo_intent)
    rows = json.loads(result)
    assert [r["source_position"] for r in rows] == [1, 2]
    assert all("result" in r for r in rows)


@pytest.mark.asyncio
async def test_broadcast_unnamed_sources_have_null_name() -> None:
    # §6.1.4 — source_name reported per source (null when unnamed)
    io = StaticIOLayer({"https://x": "A"})
    result = await run("(https://x)!*'go'", io, process=echo_intent)
    rows = json.loads(result)
    assert rows[0]["source_name"] is None


@pytest.mark.asyncio
async def test_current_variable_in_broadcast_intent() -> None:
    # §6.1.2 rule 3 — $current refers to the source being processed
    io = StaticIOLayer({"https://x": "A", "https://y": "B"})
    result = await run("(https://x, https://y)!*'V $current'", io, process=echo_intent)
    rows = json.loads(result)
    assert [r["result"] for r in rows] == ["V A", "V B"]


@pytest.mark.asyncio
async def test_broadcast_param_equivalent_to_star_operator() -> None:
    # §6.1.1 — `!*` MUST produce the same behavior as `! intent ; broadcast`
    io = StaticIOLayer({"https://x": "A", "https://y": "B"})
    star = await run("(https://x, https://y)!*'go'", io, process=echo_intent)
    param = await run("(https://x, https://y)!'go';broadcast", io, process=echo_intent)
    assert json.loads(star) == json.loads(param)
