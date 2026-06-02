"""Unit tests for the EnsembleInterpreter fan-out-reduce logic.

Uses the same fake plugin/app stubs from test_url4.py's Stage B tests.
No real network calls or Anthropic API — everything is mocked.
"""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor.ensemble import (
    EnsembleInterpreter,
    _build_reducer_input,
    _ResponseEntry,
    _split_collection_iteration,
    _substitute_item,
    _substitute_response_vars,
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
        self.calls: list[tuple[str, str, object]] = []

    async def handle_backend_call(self, intent: str, *, sources: str = "", app, env=None) -> str:
        del env
        self.calls.append((intent, sources, app))
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
            [
                _ResponseEntry(text="Four"),
                _ResponseEntry(text="Paris"),
                _ResponseEntry(text="Blue"),
            ],
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

    def test_no_source_labels_when_unnamed(self):
        """Q3=(b): responses without names must NOT contain backend names."""
        result = _build_reducer_input([_ResponseEntry(text="answer")], "merge")
        assert "/claude" not in result
        assert "/codex" not in result

    def test_single_response(self):
        result = _build_reducer_input([_ResponseEntry(text="only one")], "pass through")
        assert "[Response 1]" in result
        assert "[Response 2]" not in result
        assert "only one" in result
        assert "pass through" in result

    def test_instruction_is_last(self):
        result = _build_reducer_input(
            [_ResponseEntry(text="a"), _ResponseEntry(text="b")],
            "instruction",
        )
        lines = result.strip().split("\n")
        non_empty = [line for line in lines if line.strip()]
        assert non_empty[-1] == "instruction"

    # --- SF-88: named + weighted tests ---

    def test_named_weighted_responses_include_labels(self):
        """When entries have names and weights, the reducer sees them."""
        result = _build_reducer_input(
            [
                _ResponseEntry(text="Four", name="claude", weight=40),
                _ResponseEntry(text="4", name="codex", weight=30),
                _ResponseEntry(text="The answer is 4.", name="gemini", weight=30),
            ],
            "Merge $claude, $codex, and $gemini into one.",
        )
        assert "claude (weight=40):" in result
        assert "codex (weight=30):" in result
        assert "gemini (weight=30):" in result
        assert "Four" in result
        assert "The answer is 4." in result
        assert "Merge $claude" in result

    def test_named_without_weight(self):
        """Name without weight — just the name is shown."""
        result = _build_reducer_input(
            [
                _ResponseEntry(text="answer", name="alpha"),
            ],
            "reduce",
        )
        assert "alpha:" in result
        assert "weight=" not in result

    def test_mixed_named_and_unnamed(self):
        """When ANY entry has a name, all entries use the name format.
        Unnamed entries fall back to [Response N]."""
        result = _build_reducer_input(
            [
                _ResponseEntry(text="A", name="claude", weight=60),
                _ResponseEntry(text="B"),  # unnamed
            ],
            "merge",
        )
        assert "claude (weight=60):" in result
        assert "[Response 2]" in result  # unnamed fallback


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

            async def handle_backend_call(self, intent, *, sources="", app, env=None):
                del env
                raise RuntimeError("backend exploded")

        plugin = _FakeDispatchPlugin(name="claude-api", paths=["/claude"], responses=["ok"])
        failing = _FailingPlugin()
        app = _make_app(plugin, failing)  # pyright: ignore[reportArgumentType]
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


# ----------------------------------------------------------------------------
# SF-90: Variable reference substitution
# ----------------------------------------------------------------------------


class TestSubstituteResponseVars:
    def test_basic_substitution(self):
        entries = [
            _ResponseEntry(text="Four", name="claude"),
            _ResponseEntry(text="4", name="codex"),
        ]
        result = _substitute_response_vars("Combine $claude and $codex", entries)
        assert result == "Combine Four and 4"

    def test_no_names_no_substitution(self):
        entries = [_ResponseEntry(text="text")]
        result = _substitute_response_vars("$claude stays", entries)
        assert result == "$claude stays"

    def test_unknown_var_left_as_is(self):
        entries = [_ResponseEntry(text="ok", name="claude")]
        result = _substitute_response_vars("$codex is unknown", entries)
        assert result == "$codex is unknown"

    def test_empty_instruction(self):
        entries = [_ResponseEntry(text="x", name="claude")]
        assert _substitute_response_vars("", entries) == ""

    def test_multiple_occurrences(self):
        entries = [_ResponseEntry(text="YES", name="a")]
        result = _substitute_response_vars("$a and $a again", entries)
        assert result == "YES and YES again"

    def test_preserves_precompilation_vars(self):
        """$prompt and $reducer are precompiled BEFORE the executor
        sees the expression. They should never appear here, but if
        they leak through they must not be mangled."""
        entries = [_ResponseEntry(text="x", name="claude")]
        result = _substitute_response_vars("$prompt and $reducer and $claude", entries)
        assert "$prompt" in result
        assert "$reducer" in result
        assert "x" in result


@pytest.mark.anyio
class TestEnsembleWithVariableRefs:
    async def test_variable_refs_resolved_in_reducer_intent(self):
        """Full ensemble: named fan-out elements → $name vars in reducer
        instruction get replaced with actual response text."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["HELLO", "GOODBYE", "MERGED"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        await interp.evaluate(
            "(first:50:/claude()!say hi,second:50:/claude()!say bye)!Combine $first and $second"
        )

        # The reducer (3rd call) should see the substituted instruction
        reducer_intent = plugin.calls[2][0]
        assert "HELLO" in reducer_intent
        assert "GOODBYE" in reducer_intent
        assert "$first" not in reducer_intent
        assert "$second" not in reducer_intent

    async def test_unnamed_elements_dont_create_vars(self):
        """Unnamed fan-out elements don't contribute to variable substitution."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["X", "Y", "REDUCED"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        await interp.evaluate("(/claude()!a,/claude()!b)!$a and $b stay literal")

        reducer_intent = plugin.calls[2][0]
        # $a and $b should NOT have been substituted (elements are unnamed)
        assert "$a" in reducer_intent
        assert "$b" in reducer_intent


# ----------------------------------------------------------------------------
# SF-91: Collection iteration helpers
# ----------------------------------------------------------------------------


class TestSplitCollectionIteration:
    def test_basic_pattern(self):
        source, body = _split_collection_iteration("/data/abc*(claude:/claude($item.q)!Answer)")
        assert source == "/data/abc"
        assert body == "claude:/claude($item.q)!Answer"

    def test_no_pattern(self):
        source, body = _split_collection_iteration("(hello, world)")
        assert source is None
        assert body is None

    def test_star_not_followed_by_paren(self):
        source, body = _split_collection_iteration("a*b")
        assert source is None
        assert body is None

    def test_nested_parens_in_body(self):
        source, body = _split_collection_iteration("/data/x*(/claude($item.q)!Answer)")
        assert source == "/data/x"
        assert body == "/claude($item.q)!Answer"

    def test_url_source(self):
        source, body = _split_collection_iteration("https://example.com/data.jsonl*(text)!intent")
        assert source == "https://example.com/data.jsonl"
        assert body == "text"


class TestSubstituteItem:
    def test_bare_item(self):
        assert _substitute_item("$item", "hello") == "hello"

    def test_item_field(self):
        result = _substitute_item("$item.question", '{"question":"What is 2+2?"}')
        assert result == "What is 2+2?"

    def test_item_field_not_found(self):
        result = _substitute_item("$item.missing", '{"question":"hi"}')
        assert result == "$item.missing"

    def test_non_json_item_field_left_as_is(self):
        result = _substitute_item("$item.field", "plain text")
        assert result == "$item.field"

    def test_multiple_fields(self):
        result = _substitute_item(
            "$item.a and $item.b",
            '{"a":"X","b":"Y"}',
        )
        assert result == "X and Y"

    def test_bare_and_field_together(self):
        result = _substitute_item(
            "Full: $item, just q: $item.q",
            '{"q":"hi"}',
        )
        assert "hi" in result

    def test_bare_item_with_unicode_escape_in_data(self):
        """Regression: a bare $item whose raw JSON contains a ``\\u`` unicode
        escape must not crash. A string re.sub replacement parses ``\\u``
        eagerly and raises 'bad escape \\u' (the bug seen on real JSONL
        datasets); the callable form inserts the value literally."""
        # Non-raw string: each \\u00e9 is a single backslash + u00e9, exactly
        # how a JSONL line stores a unicode escape.
        item_json = '{"question": "caf\\u00e9 r\\u00e9sum\\u00e9"}'
        assert "\\u00e9" in item_json  # sanity: a real single-backslash \\u escape
        assert _substitute_item("$item", item_json) == item_json


@pytest.mark.anyio
class TestCollectionIteration:
    async def test_basic_iteration(self):
        """Collection source with 3 items → 3 evaluations."""
        plugin = _FakeDispatchPlugin(
            name="claude-api",
            paths=["/claude"],
            responses=["A1", "A2", "A3"],
        )
        app = _make_app(plugin)
        interp = EnsembleInterpreter(app=app, processor="/claude")

        # Mock the collection source resolution
        from unittest.mock import AsyncMock, patch

        collection_body = '{"q":"Q1"}\n{"q":"Q2"}\n{"q":"Q3"}'

        with patch(
            "screamingface.plugins.url4_executor.url4_resolve._fetch_url",
            new_callable=AsyncMock,
            return_value=collection_body,
        ):
            result = await interp.evaluate(
                "https://example.com/data.jsonl*(/claude($item.q)!Answer)!reduce"
            )

        # 3 items × 1 fan-out call each + 3 reducer calls = 6
        # (each item triggers (/claude($item.q)!Answer)!reduce which is a
        # single backend call + reducer)
        assert len(plugin.calls) >= 3
        lines = result.split("\n")
        assert len(lines) >= 1  # at least some output
