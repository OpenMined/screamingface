# pyright: reportAttributeAccessIssue=false
"""Tests for DEMO-005 (SF-152) named bindings."""

from __future__ import annotations

import asyncio

import pytest

from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4Binding,
    Url4List,
    Url4RelUrl,
    Url4Text,
    Url4Url,
    parse,
)
from screamingface.plugins.url4_executor.url4_resolve import resolve

# ---------------------------------------------------------------------------
# AST node
# ---------------------------------------------------------------------------


def test_url4_binding_carries_name_value_kind() -> None:
    node = Url4Binding(name="x", value=Url4Text(value="1"), kind="=")
    assert node.name == "x"
    assert node.kind == "="
    assert isinstance(node.value, Url4Text)


def test_url4_binding_is_frozen() -> None:
    node = Url4Binding(name="x", value=Url4Text(value="1"), kind="=")
    with pytest.raises(Exception):  # FrozenInstanceError
        node.name = "y"  # type: ignore[misc]


def test_url4_binding_supports_colon_kind() -> None:
    node = Url4Binding(name="x", value=Url4Text(value="1"), kind=":")
    assert node.kind == ":"


# ---------------------------------------------------------------------------
# Parser — name=expr (eager value bind)
# ---------------------------------------------------------------------------


def test_parse_eq_binding_text_value() -> None:
    node = parse("a=1")
    assert isinstance(node, Url4Binding)
    assert node.name == "a"
    assert node.kind == "="
    assert isinstance(node.value, Url4Text)
    assert node.value.value == "1"


def test_parse_eq_binding_url_value() -> None:
    node = parse("doc=https://example.com/x")
    assert isinstance(node, Url4Binding)
    assert node.name == "doc"
    assert node.kind == "="
    assert isinstance(node.value, Url4Url)


def test_parse_eq_binding_relurl_value() -> None:
    node = parse("doc=/data/foo")
    assert isinstance(node, Url4Binding)
    assert isinstance(node.value, Url4RelUrl)
    assert node.value.value == "/data/foo"


def test_parse_eq_binding_backend_call_value() -> None:
    node = parse("ans=/claude()!summarize")
    assert isinstance(node, Url4Binding)
    assert isinstance(node.value, Url4BackendCall)
    assert node.value.path == "/claude"


def test_parse_eq_binding_group_value() -> None:
    node = parse("pair=(a, b)")
    assert isinstance(node, Url4Binding)
    assert isinstance(node.value, Url4List)
    assert len(node.value.items) == 2


def test_parse_list_of_eq_bindings() -> None:
    node = parse("(a=1, b=2)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert all(isinstance(it, Url4Binding) for it in node.items)
    a, b = node.items
    assert a.name == "a" and b.name == "b"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Parser — name:(...) (subexpression label)
# ---------------------------------------------------------------------------


def test_parse_colon_binding_with_group() -> None:
    node = parse("normalized:(/claude()!x, /codex()!y)")
    assert isinstance(node, Url4Binding)
    assert node.name == "normalized"
    assert node.kind == ":"
    assert isinstance(node.value, Url4List)
    assert len(node.value.items) == 2
    assert all(isinstance(it, Url4BackendCall) for it in node.value.items)


def test_parse_colon_binding_in_list() -> None:
    node = parse("(normalized:(a, b), consensus:(c, d))")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert all(isinstance(it, Url4Binding) and it.kind == ":" for it in node.items)


# ---------------------------------------------------------------------------
# Disambiguation — source_label on backend_call must NOT become a binding
# ---------------------------------------------------------------------------


def test_weighted_backend_call_still_parses_as_backend_call() -> None:
    """`claude:0.40:/claude()!x` MUST remain a Url4BackendCall, not a binding."""
    node = parse("claude:0.40:/claude()!x")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/claude"
    assert node.name == "claude"
    assert node.weight == 0.40


def test_integer_weight_backend_call() -> None:
    node = parse("a:40:/claude()!hi")
    assert isinstance(node, Url4BackendCall)
    assert node.name == "a"
    assert node.weight == 40.0


def test_colon_binding_does_not_swallow_numeric_label() -> None:
    """If the body after `:` starts with a digit, it must NOT match `binding`."""
    node = parse("claude:0.40:/claude()!hi")
    assert not isinstance(node, Url4Binding)


# ---------------------------------------------------------------------------
# Resolver — eager bindings + two-pass list resolution
# ---------------------------------------------------------------------------


def test_resolve_eq_binding_returns_resolved_value() -> None:
    result = asyncio.run(resolve(parse("greet=hello"), app=None, env=Env.root()))
    assert result == "hello"


def test_resolve_colon_binding_returns_resolved_group() -> None:
    result = asyncio.run(resolve(parse("pair:(hello, world)"), app=None, env=Env.root()))
    assert result == "hello\nworld"


def test_list_with_binding_preserves_source_order() -> None:
    # "let" semantics: binding (x=hi) sets up scope; the non-binding body
    # ("plain") is the sole output.  The binding value is NOT echoed.
    result = asyncio.run(resolve(parse("(x=hi, plain)"), app=None, env=Env.root()))
    assert result == "plain"


def test_list_bindings_resolved_before_non_bindings() -> None:
    # "let" semantics: bindings a=1, b=2 are set up first; only the
    # non-binding body item "c" appears in the output.
    result = asyncio.run(resolve(parse("(a=1, b=2, c)"), app=None, env=Env.root()))
    assert result == "c"


def test_list_without_bindings_unchanged() -> None:
    """Lists with no bindings must behave exactly like the old gather path."""
    result = asyncio.run(resolve(parse("(a, b, c)"), app=None, env=Env.root()))
    assert result == "a\nb\nc"
