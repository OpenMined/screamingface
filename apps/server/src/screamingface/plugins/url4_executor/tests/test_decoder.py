"""Unit tests for split_intent in decoder.py.

Most of the existing url4 tests exercise split_intent indirectly via
the /ensemble HTTP route. These tests pin down its exact behavior at the
function level — especially the SF-79 Stage B backend-call awareness and
SF-93 intent broadcasting.
"""

from __future__ import annotations

from screamingface.plugins.url4_executor.decoder import split_intent

# ----------------------------------------------------------------------------
# Pre-existing behavior — preserved (now returns 3-tuple with broadcast=False)
# ----------------------------------------------------------------------------


class TestExistingBehavior:
    def test_no_intent_returns_expr_unchanged(self):
        assert split_intent("hello world") == ("hello world", None, False)

    def test_top_level_intent_split(self):
        assert split_intent("(https://ex.com)!summarize") == (
            "(https://ex.com)",
            "summarize",
            False,
        )

    def test_intent_inside_parens_not_split(self):
        assert split_intent("(a!b)") == ("(a!b)", None, False)

    def test_first_top_level_bang_wins(self):
        assert split_intent("a!b!c") == ("a", "b!c", False)

    def test_empty_expression(self):
        assert split_intent("") == ("", None, False)


# ----------------------------------------------------------------------------
# SF-79 Stage B — backend-call awareness
# ----------------------------------------------------------------------------


class TestBackendCallAwareness:
    def test_top_level_backend_call_with_intent_not_split(self):
        assert split_intent("/claude()!hello") == ("/claude()!hello", None, False)

    def test_top_level_backend_call_without_intent_unchanged(self):
        assert split_intent("/claude()") == ("/claude()", None, False)

    def test_backend_call_with_relurl_intent(self):
        assert split_intent("/claude()!/data/abc123") == (
            "/claude()!/data/abc123",
            None,
            False,
        )

    def test_backend_call_then_top_level_bang(self):
        source, intent, broadcast = split_intent("/claude()!hello!reduce")
        assert source == "/claude()!hello"
        assert intent == "reduce"
        assert broadcast is False

    def test_fan_out_list_with_backend_calls_then_outer_intent(self):
        expr = "(/claude()!a, /claude()!b, /claude()!c)!reduce"
        source, intent, broadcast = split_intent(expr)
        assert source == "(/claude()!a, /claude()!b, /claude()!c)"
        assert intent == "reduce"
        assert broadcast is False

    def test_paren_group_with_inner_backend_calls_not_split_at_inner_bangs(self):
        expr = "(/claude()!a, /claude()!b)"
        assert split_intent(expr) == (expr, None, False)

    def test_backend_call_with_text_intent_containing_bang(self):
        source, intent, broadcast = split_intent("/claude()!some!text")
        assert source == "/claude()!some"
        assert intent == "text"
        assert broadcast is False

    def test_double_paren_close_then_bang_does_split(self):
        expr = "(/claude())!intent"
        source, intent, broadcast = split_intent(expr)
        assert source == "(/claude())"
        assert intent == "intent"
        assert broadcast is False

    def test_bare_parens_then_bang_skipped(self):
        source, intent, broadcast = split_intent("()!x")
        assert source == "()!x"
        assert intent is None
        assert broadcast is False


# ----------------------------------------------------------------------------
# SF-93: Intent broadcasting — !* operator
# ----------------------------------------------------------------------------


class TestIntentBroadcasting:
    def test_broadcast_operator_detected(self):
        source, intent, broadcast = split_intent("(a, b, c)!*uppercase")
        assert source == "(a, b, c)"
        assert intent == "uppercase"
        assert broadcast is True

    def test_broadcast_with_quoted_intent(self):
        source, intent, broadcast = split_intent("(a, b)!*'Extract the color word'")
        assert source == "(a, b)"
        assert intent == "'Extract the color word'"
        assert broadcast is True

    def test_broadcast_no_intent_text_after_star(self):
        """!* with nothing after the * — empty intent, broadcast True."""
        source, intent, broadcast = split_intent("(a, b)!*")
        assert source == "(a, b)"
        assert intent == ""
        assert broadcast is True

    def test_broadcast_with_backend_calls(self):
        """Fan-out list with !* — intent broadcast across backend calls."""
        expr = "(/claude()!a, /claude()!b)!*validate"
        source, intent, broadcast = split_intent(expr)
        assert source == "(/claude()!a, /claude()!b)"
        assert intent == "validate"
        assert broadcast is True

    def test_regular_bang_not_broadcast(self):
        """Confirm ! without * is not broadcast."""
        _, _, broadcast = split_intent("(a, b)!reduce")
        assert broadcast is False

    def test_star_inside_intent_not_broadcast(self):
        """A * later in the intent text is not a broadcast marker.
        Only !* at the split point triggers broadcast."""
        source, intent, broadcast = split_intent("(a)!hello*world")
        assert source == "(a)"
        assert intent == "hello*world"
        assert broadcast is False
