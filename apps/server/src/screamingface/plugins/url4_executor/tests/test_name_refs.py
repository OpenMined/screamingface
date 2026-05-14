# pyright: reportAttributeAccessIssue=false
"""Tests for DEMO-006 (SF-149): $<name> resolution + multi-segment $item.dotted."""

from __future__ import annotations

import asyncio

from screamingface.plugins.url4_executor.ensemble_helpers import (
    FanoutResponse,
    substitute_env_vars,
    substitute_item,
    substitute_response_vars,
)
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import parse
from screamingface.plugins.url4_executor.url4_resolve import resolve

# ---------------------------------------------------------------------------
# substitute_env_vars — env-only $name substitution
# ---------------------------------------------------------------------------


def test_env_vars_replaces_known_name() -> None:
    env = Env.root().child(consensus="the answer is 42")
    assert substitute_env_vars("reduce: $consensus", env) == "reduce: the answer is 42"


def test_env_vars_walks_parent_chain() -> None:
    env = Env.root().child(outer="hi").child(inner="lo")
    assert substitute_env_vars("$outer $inner", env) == "hi lo"


def test_env_vars_leaves_unknown_literal() -> None:
    env = Env.root().child(x="1")
    assert substitute_env_vars("$unknown $x", env) == "$unknown 1"


def test_env_vars_none_env_is_noop() -> None:
    assert substitute_env_vars("plain $x text", None) == "plain $x text"


def test_env_vars_empty_string_is_noop() -> None:
    assert substitute_env_vars("", Env.root().child(x="1")) == ""


def test_env_vars_only_matches_word_boundaries() -> None:
    """`$consensus` must not bleed into `$consensus_thing`."""
    env = Env.root().child(consensus="X", consensus_thing="Y")
    assert substitute_env_vars("$consensus $consensus_thing", env) == "X Y"


def test_env_vars_non_string_value_is_json_encoded() -> None:
    env = Env.root().child(nums=[1, 2, 3])
    assert substitute_env_vars("got $nums", env) == "got [1, 2, 3]"


# ---------------------------------------------------------------------------
# substitute_response_vars — env-first fallback to entries
# ---------------------------------------------------------------------------


def test_response_vars_env_hit_wins_over_entries() -> None:
    entries = [FanoutResponse(text="from-entry", name="x")]
    env = Env.root().child(x="from-env")
    assert substitute_response_vars("$x", entries, env=env) == "from-env"


def test_response_vars_entries_used_when_env_misses() -> None:
    entries = [FanoutResponse(text="from-entry", name="x")]
    env = Env.root().child(y="other")
    assert substitute_response_vars("$x", entries, env=env) == "from-entry"


def test_response_vars_all_miss_leaves_literal() -> None:
    entries = [FanoutResponse(text="t", name="other")]
    env = Env.root().child(y="other")
    assert substitute_response_vars("$x stays", entries, env=env) == "$x stays"


def test_response_vars_no_env_param_is_backward_compatible() -> None:
    entries = [FanoutResponse(text="hi", name="claude")]
    assert substitute_response_vars("$claude!", entries) == "hi!"


def test_response_vars_env_only_no_matching_entry() -> None:
    env = Env.root().child(consensus="combined")
    assert substitute_response_vars("reduce: $consensus", [], env=env) == "reduce: combined"


# ---------------------------------------------------------------------------
# substitute_item — multi-segment dotted
# ---------------------------------------------------------------------------


def test_item_three_segment_hit() -> None:
    assert substitute_item("$item.a.b.c", '{"a":{"b":{"c":"x"}}}') == "x"


def test_item_two_segment_hit() -> None:
    assert substitute_item("$item.user.name", '{"user":{"name":"Alice"}}') == "Alice"


def test_item_three_segment_graceful_miss_intermediate_not_dict() -> None:
    assert substitute_item("$item.a.b.c", '{"a":1}') == "$item.a.b.c"


def test_item_three_segment_graceful_miss_terminal_absent() -> None:
    assert substitute_item("$item.a.b.c", '{"a":{"b":{"d":1}}}') == "$item.a.b.c"


def test_item_multi_segment_non_string_value_json_encoded() -> None:
    assert substitute_item("$item.a.b", '{"a":{"b":[1,2,3]}}') == "[1, 2, 3]"


def test_item_single_segment_still_works() -> None:
    assert substitute_item("$item.q", '{"q":"hi"}') == "hi"


def test_item_bare_item_still_works() -> None:
    assert substitute_item("$item", "raw") == "raw"


def test_item_field_inside_text_still_works() -> None:
    assert substitute_item("Q: $item.q.", '{"q":"hello"}') == "Q: hello."


# ---------------------------------------------------------------------------
# Url4Text resolution — env-aware substitution
# ---------------------------------------------------------------------------


def test_url4_text_substitutes_env_name() -> None:
    env = Env.root().child(greeting="hello")
    result = asyncio.run(resolve(parse("$greeting world"), app=None, env=env))
    assert result == "hello world"


def test_url4_text_unknown_name_left_literal() -> None:
    result = asyncio.run(resolve(parse("$unknown stays"), app=None, env=Env.root()))
    assert result == "$unknown stays"


def test_list_binding_visible_to_sibling_text() -> None:
    """`(x=hi, see $x)` — pass 1 binds, pass 2 reads via env."""
    result = asyncio.run(resolve(parse("(x=hi, see $x)"), app=None, env=Env.root()))
    assert result == "hi\nsee hi"
