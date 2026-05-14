# pyright: reportAttributeAccessIssue=false
"""Tests for DEMO-007 (SF-154): `.py` paths rewrite to `/python` backend calls."""

from __future__ import annotations

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.routes import _ast_to_dict
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4List,
    Url4RelUrl,
    parse,
)


def test_plain_py_path_rewrites_to_python_backend_call() -> None:
    node = parse("/data/check_correct.py")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/python"
    assert node.packed_context == "/data/check_correct.py"
    assert node.intent is None
    assert node.name is None
    assert node.weight is None


def test_py_path_inside_list_rewrites() -> None:
    node = parse("(/foo, /bar.py)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    foo, bar = node.items
    assert isinstance(foo, Url4RelUrl)
    assert foo.value == "/foo"
    assert isinstance(bar, Url4BackendCall)
    assert bar.path == "/python"
    assert bar.packed_context == "/bar.py"


def test_py_path_as_intent_rewrites() -> None:
    """`(a, b)!/data/x.py` — after split_intent, parsing the intent yields a /python call."""
    source_expr, intent, _broadcast = split_intent("(a, b)!/data/check_correct.py")
    assert source_expr == "(a, b)"
    assert intent == "/data/check_correct.py"
    intent_node = parse(intent)
    assert isinstance(intent_node, Url4BackendCall)
    assert intent_node.path == "/python"
    assert intent_node.packed_context == "/data/check_correct.py"


def test_non_py_relurl_unchanged() -> None:
    node = parse("/something/not-py")
    assert isinstance(node, Url4RelUrl)
    assert node.value == "/something/not-py"


def test_py_in_middle_of_path_is_not_rewritten() -> None:
    """Only paths ENDING in `.py` rewrite. `/foo.py/bar` is a normal relurl."""
    node = parse("/foo.py/bar")
    assert isinstance(node, Url4RelUrl)
    assert node.value == "/foo.py/bar"


def test_root_py_path_rewrites() -> None:
    node = parse("/x.py")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/python"
    assert node.packed_context == "/x.py"


def test_ast_to_dict_serializes_rewritten_node() -> None:
    node = parse("/data/x.py")
    d = _ast_to_dict(node)
    assert d == {
        "type": "backend_call",
        "path": "/python",
        "packed_context": "/data/x.py",
    }


def test_https_py_url_is_not_rewritten() -> None:
    """Absolute ``https://...`` URLs are NOT rewritten — remote scripts out of scope."""
    from screamingface.plugins.url4_executor.url4 import Url4Url

    node = parse("https://example.com/x.py")
    assert isinstance(node, Url4Url)
    assert node.value == "https://example.com/x.py"
