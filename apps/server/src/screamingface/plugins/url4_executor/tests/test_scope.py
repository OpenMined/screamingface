"""Unit tests for the Env scope chain (DEMO-004)."""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor.scope import Env


def test_root_is_empty():
    env = Env.root()
    assert env.bindings == {}
    assert env.parent is None


def test_lookup_finds_binding_in_current_frame():
    env = Env.root().child(a=1)
    assert env.lookup("a") == 1


def test_lookup_walks_parent_chain():
    env = Env.root().child(a=1).child(b=2)
    assert env.lookup("a") == 1
    assert env.lookup("b") == 2


def test_lookup_missing_name_raises_keyerror():
    env = Env.root().child(a=1)
    with pytest.raises(KeyError):
        env.lookup("nope")


def test_child_does_not_mutate_parent():
    parent = Env.root().child(a=1)
    parent_snapshot = dict(parent.bindings)
    _ = parent.child(b=2)
    assert parent.bindings == parent_snapshot


def test_inner_binding_shadows_outer():
    env = Env.root().child(x="outer").child(x="inner")
    assert env.lookup("x") == "inner"


def test_env_is_frozen():
    env = Env.root()
    with pytest.raises(Exception):  # FrozenInstanceError, but don't tie test to dataclass internals
        env.parent = Env.root()  # type: ignore[misc]


def test_child_accepts_arbitrary_value_types():
    """Bindings values are typed Any — strings now, possibly AST nodes later."""
    env = Env.root().child(s="hi", n=42, lst=[1, 2, 3])
    assert env.lookup("s") == "hi"
    assert env.lookup("n") == 42
    assert env.lookup("lst") == [1, 2, 3]
