"""Unit tests for the EnsembleInterpreter fan-out-reduce logic.

Uses the same fake plugin/app stubs from test_url4.py's Stage B tests.
No real network calls or Anthropic API — everything is mocked.
"""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor.ensemble import (
    EnsembleInterpreter,
    _build_reducer_input,
)
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4List,
    Url4Text,
)

# ----------------------------------------------------------------------------
# Fake plugin stubs (same as test_url4.py Stage B tests)
# ----------------------------------------------------------------------------


class _FakePluginRegistry:
    def __init__(self, active: dict) -> None:
        self.active_plugins = active


class _FakeAppState:
    def __init__(self, plugins: _FakePluginRegistry) -> None:
        self.plugins = plugins


class _FakeApp:
    def __init__(self, plugins: _FakePluginRegistry) -> None:
        self.state = _FakeAppState(plugins)


class _FakeDispatchPlugin:
    """Plugin stub that records calls and returns canned responses.

    If ``responses`` is a list, returns them in order (round-robin for
    calls beyond the list length). If a single string, returns it every time.
    """

    def __init__(
        self,
        name: str,
        paths: list[str],
        responses: str | list[str],
    ) -> None:
        self.name = name
        self.backend_call_paths = paths
        self._responses = responses if isinstance(responses, list) else [responses]
        self._call_idx = 0
        self.calls: list[tuple[str, object]] = []

    async def handle_backend_call(self, intent: str, *, app) -> str:
        self.calls.append((intent, app))
        resp = self._responses[self._call_idx % len(self._responses)]
        self._call_idx += 1
        return resp


def _make_app(*plugins: _FakeDispatchPlugin) -> _FakeApp:
    registry = _FakePluginRegistry({p.name: p for p in plugins})
    return _FakeApp(registry)


# ----------------------------------------------------------------------------
# _is_fanout tests
# ----------------------------------------------------------------------------


class TestIsFanout:
    def test_list_of_all_backend_calls_is_fanout(self):
        node = Url4List(
            items=(
                Url4BackendCall(path="/claude", intent=Url4Text(value="a")),
                Url4BackendCall(path="/codex", intent=Url4Text(value="b")),
            )
        )
        assert EnsembleInterpreter._is_fanout(node) is True

    def test_list_with_mixed_types_is_not_fanout(self):
        node = Url4List(
            items=(
                Url4BackendCall(path="/claude", intent=Url4Text(value="a")),
                Url4Text(value="plain text"),
            )
        )
        assert EnsembleInterpreter._is_fanout(node) is False

    def test_empty_list_is_not_fanout(self):
        node = Url4List(items=())
        assert EnsembleInterpreter._is_fanout(node) is False

    def test_single_backend_call_not_in_list_is_not_fanout(self):
        node = Url4BackendCall(path="/claude", intent=Url4Text(value="a"))
        assert EnsembleInterpreter._is_fanout(node) is False

    def test_text_node_is_not_fanout(self):
        node = Url4Text(value="hello")
        assert EnsembleInterpreter._is_fanout(node) is False


# ----------------------------------------------------------------------------
# _build_reducer_input tests
# ----------------------------------------------------------------------------


class TestBuildReducerInput:
    def test_three_responses_unlabeled(self):
        result = _build_reducer_input(
            ["Four", "Paris", "Blue"],
            "Combine these facts.",
        )
        assert "[Response 1]" in result
        assert "[Response 2]" in result
        assert "[Response 3]" in result
        assert "Four" in result
        assert "Paris" in result
        assert "Blue" in result
        assert "[Instruction]" in result
        assert "Combine these facts." in result

    def test_no_source_labels(self):
        """Q3=(b): responses must NOT contain backend names."""
        result = _build_reducer_input(["answer"], "merge")
        assert "/claude" not in result
        assert "/codex" not in result
        assert "from" not in result.lower().split("[response")[0]

    def test_single_response(self):
        result = _build_reducer_input(["only one"], "pass through")
        assert "[Response 1]" in result
        assert "[Response 2]" not in result
        assert "only one" in result
        assert "pass through" in result

    def test_instruction_is_last(self):
        result = _build_reducer_input(["a", "b"], "instruction")
        lines = result.strip().split("\n")
        # Last non-empty line should be the instruction
        non_empty = [line for line in lines if line.strip()]
        assert non_empty[-1] == "instruction"


# ----------------------------------------------------------------------------
# Full ensemble evaluate tests
# ----------------------------------------------------------------------------


@pytest.mark.anyio
class TestEnsembleEvaluate:
    async def test_fanout_dispatches_n_calls(self):
        """Three fan-out elements → backend called 3 times."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["resp1", "resp2", "resp3"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        await interp.evaluate(
            "(/claude()!question1, /claude()!question2, /claude()!question3)!Combine these."
        )

        # 3 fan-out calls + 1 reducer call = 4 total
        assert len(plugin.calls) == 4
        # First 3 are the fan-out intents
        assert plugin.calls[0][0] == "question1"
        assert plugin.calls[1][0] == "question2"
        assert plugin.calls[2][0] == "question3"

    async def test_reducer_receives_all_responses(self):
        """The reducer call (4th) receives all three fan-out responses."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["alpha", "beta", "gamma", "REDUCED"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        await interp.evaluate("(/claude()!a, /claude()!b, /claude()!c)!Merge them.")

        # 4th call is the reducer
        reducer_intent = plugin.calls[3][0]
        assert "alpha" in reducer_intent
        assert "beta" in reducer_intent
        assert "gamma" in reducer_intent
        assert "Merge them." in reducer_intent

    async def test_reducer_instruction_from_outer_intent(self):
        """The outer !"..." string becomes the reducer's instruction."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["x", "REDUCED"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        await interp.evaluate("(/claude()!q)!Synthesize into one coherent answer.")

        reducer_intent = plugin.calls[1][0]
        assert "Synthesize into one coherent answer." in reducer_intent

    async def test_returns_reducer_response(self):
        """The ensemble's return value is the reducer's output."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["fan1", "fan2", "THE FINAL ANSWER"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        result = await interp.evaluate("(/claude()!a, /claude()!b)!reduce")

        assert result == "THE FINAL ANSWER"

    async def test_processor_param_routes_reducer(self):
        """The processor path determines which backend runs the reducer."""
        fanout_plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["response"],
        )
        reducer_plugin = _FakeDispatchPlugin(
            name="codex-api",
            paths=["/codex"],
            responses=["CODEX REDUCED"],
        )
        app = _make_app(fanout_plugin, reducer_plugin)
        interp = EnsembleInterpreter(app=app, processor="/codex")

        result = await interp.evaluate("(/claude()!question)!reduce")

        # Fan-out went to /claude
        assert len(fanout_plugin.calls) == 1
        # Reducer went to /codex
        assert len(reducer_plugin.calls) == 1
        assert result == "CODEX REDUCED"

    async def test_fanout_failure_aborts_ensemble(self):
        """Q6=(a): if any fan-out element fails, the whole ensemble aborts."""

        class _FailingPlugin:
            name = "failing"
            backend_call_paths = ["/failing"]

            async def handle_backend_call(self, intent, *, app):
                raise RuntimeError("backend exploded")

        plugin = _FakeDispatchPlugin(name="claude-api", paths=["/claude"], responses=["ok"])
        failing = _FailingPlugin()
        app = _make_app(plugin, failing)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        with pytest.raises(RuntimeError, match="backend exploded"):
            await interp.evaluate("(/claude()!a, /failing()!b)!reduce")

        # The reducer should NOT have been called
        assert len(plugin.calls) <= 1  # at most the successful fan-out

    async def test_non_fanout_expression_falls_through(self):
        """A regular url4 expression (not a fan-out list) goes through
        the base Url4Interpreter behavior, not the ensemble path."""
        interp = EnsembleInterpreter(app=None)

        # Plain text expression — no fan-out, no backend calls.
        result = await interp.evaluate("hello world")
        assert result == "hello world"

    async def test_fanout_without_outer_intent_falls_through(self):
        """A fan-out list WITHOUT an outer !"..." instruction is not
        treated as ensemble — no reducer to call."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["response"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        # No outer intent — the list resolves via base path
        # (Stage B dispatch, results joined by newlines)
        result = await interp.evaluate("(/claude()!a, /claude()!b)")
        assert result == "response\nresponse"
        # Only 2 calls (no reducer)
        assert len(plugin.calls) == 2

    async def test_single_element_fanout_still_reduces(self):
        """N=1 degenerate fan-out: one backend call + reducer."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["solo answer", "REDUCED"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        result = await interp.evaluate("(/claude()!q)!reduce")

        assert result == "REDUCED"
        assert len(plugin.calls) == 2  # 1 fan-out + 1 reducer
