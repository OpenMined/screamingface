"""Unit tests for split_intent in decoder.py.

Most of the existing url4 tests exercise split_intent indirectly via
the /ensemble HTTP route. These tests pin down its exact behavior at the
function level — especially the SF-79 Stage B backend-call awareness.
"""

from __future__ import annotations

from screamingface.plugins.url4_executor.decoder import split_intent

# ----------------------------------------------------------------------------
# Pre-existing behavior — preserved
# ----------------------------------------------------------------------------


class TestExistingBehavior:
    def test_no_intent_returns_expr_unchanged(self):
        assert split_intent("hello world") == ("hello world", None)

    def test_top_level_intent_split(self):
        assert split_intent("(https://ex.com)!summarize") == (
            "(https://ex.com)",
            "summarize",
        )

    def test_intent_inside_parens_not_split(self):
        # The ! is inside the group, depth=1, ignored as a separator
        assert split_intent("(a!b)") == ("(a!b)", None)

    def test_first_top_level_bang_wins(self):
        assert split_intent("a!b!c") == ("a", "b!c")

    def test_empty_expression(self):
        assert split_intent("") == ("", None)


# ----------------------------------------------------------------------------
# SF-79 Stage B — backend-call awareness
# ----------------------------------------------------------------------------


class TestBackendCallAwareness:
    def test_top_level_backend_call_with_intent_not_split(self):
        """The user-friendly form: /claude()!hello at the top level
        should stay together so the parser sees the full backend_call."""
        assert split_intent("/claude()!hello") == ("/claude()!hello", None)

    def test_top_level_backend_call_without_intent_unchanged(self):
        assert split_intent("/claude()") == ("/claude()", None)

    def test_backend_call_with_relurl_intent(self):
        """The frontend-substituted form: /claude()!/data/<key>"""
        assert split_intent("/claude()!/data/abc123") == (
            "/claude()!/data/abc123",
            None,
        )

    def test_backend_call_then_top_level_bang(self):
        """``/claude()!hello!reduce`` — the first ! after () is part of
        the backend_call, but the second ! is a real top-level split."""
        # With our rule, the ! after ()/i=9 is skipped (preceded by ()),
        # then the next ! at i=15 is checked: preceded by 'lo' not '()',
        # so it splits.
        source, intent = split_intent("/claude()!hello!reduce")
        assert source == "/claude()!hello"
        assert intent == "reduce"

    def test_fan_out_list_with_backend_calls_then_outer_intent(self):
        """The target ensemble spec shape: outer ! is a real intent
        separator because it's preceded by `)` not `()`."""
        expr = "(/claude()!a, /claude()!b, /claude()!c)!reduce"
        source, intent = split_intent(expr)
        assert source == "(/claude()!a, /claude()!b, /claude()!c)"
        assert intent == "reduce"

    def test_paren_group_with_inner_backend_calls_not_split_at_inner_bangs(self):
        """Each ! inside the group is at depth 1, so it's ignored even
        without the new rule. The new rule doesn't change this case;
        this test pins it down for safety."""
        expr = "(/claude()!a, /claude()!b)"
        assert split_intent(expr) == (expr, None)

    def test_backend_call_with_text_intent_containing_bang(self):
        """``/claude()!some!text`` — the second ! is part of the intent,
        not a separator. After the first ! is skipped (preceded by ()),
        we keep scanning, find the next ! preceded by 'me', and split.

        Note: this is a tradeoff. A user who literally wants 'some!text'
        as their intent has to write it inside parens or escape somehow.
        For now we accept the split-at-second-bang behavior; the doc
        in the function explains the limitation.
        """
        source, intent = split_intent("/claude()!some!text")
        assert source == "/claude()!some"
        assert intent == "text"

    def test_double_paren_close_then_bang_does_split(self):
        """``(/claude())!intent`` — the ! is preceded by ``))``, not
        ``()``, so it splits normally."""
        expr = "(/claude())!intent"
        source, intent = split_intent(expr)
        assert source == "(/claude())"
        assert intent == "intent"

    def test_bare_parens_then_bang_skipped(self):
        """Edge case: literal '()!x' with no path — the rule still skips
        the !, so the parser later fails on the malformed form. That's
        fine; it's not a user-meaningful expression."""
        source, intent = split_intent("()!x")
        assert source == "()!x"
        assert intent is None
