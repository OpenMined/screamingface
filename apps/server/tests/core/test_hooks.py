"""Tests for the hook/signal system."""

from __future__ import annotations

from screamingface.core.hooks import HookRegistry


def test_register_and_emit(hooks: HookRegistry) -> None:
    results: list[str] = []
    hooks.register("test.event", lambda: results.append("a") or "a", plugin_name="p1")
    hooks.register("test.event", lambda: results.append("b") or "b", plugin_name="p2")

    ret = hooks.emit("test.event")
    assert results == ["a", "b"]
    assert ret == ["a", "b"]


def test_priority_ordering(hooks: HookRegistry) -> None:
    order: list[int] = []
    hooks.register("test.order", lambda: order.append(2), priority=200, plugin_name="low")
    hooks.register("test.order", lambda: order.append(1), priority=50, plugin_name="high")

    hooks.emit("test.order")
    assert order == [1, 2]


def test_emit_chain(hooks: HookRegistry) -> None:
    hooks.register("test.chain", lambda value: value + 1, plugin_name="p1")
    hooks.register("test.chain", lambda value: value * 2, plugin_name="p2")

    result = hooks.emit_chain("test.chain", value=10)
    assert result == 22  # (10 + 1) * 2


def test_unregister_plugin(hooks: HookRegistry) -> None:
    hooks.register("test.event", lambda: "a", plugin_name="keep")
    hooks.register("test.event", lambda: "b", plugin_name="remove")

    hooks.unregister_plugin("remove")

    results = hooks.emit("test.event")
    assert results == ["a"]


def test_emit_nonexistent_hook(hooks: HookRegistry) -> None:
    results = hooks.emit("does.not.exist")
    assert results == []


def test_list_hook_names(hooks: HookRegistry) -> None:
    hooks.register("b.hook", lambda: None, plugin_name="p")
    hooks.register("a.hook", lambda: None, plugin_name="p")

    assert hooks.list_hook_names() == ["a.hook", "b.hook"]
