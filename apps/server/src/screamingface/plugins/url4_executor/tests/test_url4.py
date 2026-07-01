# pyright: reportAttributeAccessIssue=false, reportOperatorIssue=false
"""Tests for the url4 spec — TatSu parser + async resolver."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4List,
    Url4RelUrl,
    Url4Text,
    Url4Url,
    parse,
    resolve,
    resolve_str,
)

# ---------------------------------------------------------------------------
# Parser tests (synchronous — assert AST node types)
# ---------------------------------------------------------------------------


def test_parse_plain_string() -> None:
    node = parse("hello world")
    assert isinstance(node, Url4Text)
    assert node.value == "hello world"


def test_parse_url() -> None:
    node = parse("http://example.com/data")
    assert isinstance(node, Url4Url)
    assert node.value == "http://example.com/data"


def test_parse_https_url() -> None:
    node = parse("https://example.com/path?q=1")
    assert isinstance(node, Url4Url)
    assert node.value == "https://example.com/path?q=1"


def test_parse_single_item_list() -> None:
    node = parse("(hello)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 1
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "hello"


def test_parse_multi_item_list() -> None:
    node = parse("(http://a.com, some text, http://b.com)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Url)
    assert node.items[0].value == "http://a.com"
    assert isinstance(node.items[1], Url4Text)
    assert node.items[1].value == "some text"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "http://b.com"


def test_parse_nested_list() -> None:
    node = parse("(http://a.com, (http://b.com, inner text))")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert isinstance(node.items[1], Url4List)
    inner = node.items[1]
    assert isinstance(inner, Url4List)
    assert len(inner.items) == 2
    assert isinstance(inner.items[0], Url4Url)
    assert isinstance(inner.items[1], Url4Text)


# ---------------------------------------------------------------------------
# Parse tests for the 10 url4 examples
# ---------------------------------------------------------------------------


def test_parse_example_1() -> None:
    """(url, url) — two plain URLs."""
    node = parse("(https://docs.company.com/api, https://docs.company.com/faq)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert node.items[0].value == "https://docs.company.com/api"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://docs.company.com/faq"


def test_parse_example_2() -> None:
    """(text, url) — text prompt + URL."""
    node = parse(
        "(You are an expert Python developer.,"
        " https://raw.githubusercontent.com/org/repo/main/README.md)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "You are an expert Python developer."
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://raw.githubusercontent.com/org/repo/main/README.md"


def test_parse_example_3() -> None:
    """(text, url, url) — text + two URLs."""
    node = parse(
        "(Summarize the following:,"
        " https://docs.company.com/changelog,"
        " https://docs.company.com/migration-guide)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Summarize the following:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://docs.company.com/changelog"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://docs.company.com/migration-guide"


def test_parse_example_4() -> None:
    """(url4_url, url4_url) — nested url4 URLs with balanced parens."""
    node = parse(
        "(https://localhost:8000/ensemble?context=(https://docs.a.com, https://docs.b.com),"
        " https://localhost:8000/ensemble?context=(https://docs.c.com, https://docs.d.com))"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert (
        node.items[0].value
        == "https://localhost:8000/ensemble?context=(https://docs.a.com, https://docs.b.com)"
    )
    assert isinstance(node.items[1], Url4Url)
    assert (
        node.items[1].value
        == "https://localhost:8000/ensemble?context=(https://docs.c.com, https://docs.d.com)"
    )


def test_parse_example_5() -> None:
    """(text, url, url) — code review prompt."""
    node = parse(
        "(Review this code for security issues:,"
        " https://raw.githubusercontent.com/org/repo/main/src/auth.py,"
        " https://raw.githubusercontent.com/org/repo/main/src/session.py)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Review this code for security issues:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://raw.githubusercontent.com/org/repo/main/src/auth.py"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://raw.githubusercontent.com/org/repo/main/src/session.py"


def test_parse_example_6() -> None:
    """(text, url, text) — text + URL + text."""
    node = parse(
        "(Follow these coding standards:, https://company.com/style-guide, Always use type hints.)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Follow these coding standards:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://company.com/style-guide"
    assert isinstance(node.items[2], Url4Text)
    assert node.items[2].value == "Always use type hints."


def test_parse_example_7() -> None:
    """(url?query, url?query) — URLs with query params."""
    node = parse(
        "(https://api.github.com/repos/org/repo/releases/latest,"
        " https://api.github.com/repos/org/repo/issues?state=open)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert node.items[0].value == "https://api.github.com/repos/org/repo/releases/latest"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://api.github.com/repos/org/repo/issues?state=open"


def test_parse_example_8() -> None:
    """(text, url, url) — debugging context."""
    node = parse(
        "(You are debugging a production outage.,"
        " https://grafana.internal/api/dashboards/export,"
        " https://logs.internal/api/recent-errors)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "You are debugging a production outage."
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://grafana.internal/api/dashboards/export"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://logs.internal/api/recent-errors"


def test_parse_example_9() -> None:
    """(text, url, url, text) — project context with prompt placeholder."""
    node = parse(
        "(Project context:,"
        " https://raw.githubusercontent.com/org/repo/main/README.md,"
        " https://raw.githubusercontent.com/org/repo/main/ARCHITECTURE.md,"
        " Current task: {prompt})"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 4
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Project context:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://raw.githubusercontent.com/org/repo/main/README.md"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://raw.githubusercontent.com/org/repo/main/ARCHITECTURE.md"
    assert isinstance(node.items[3], Url4Text)
    assert node.items[3].value == "Current task: {prompt}"


def test_parse_example_10() -> None:
    """(url4_url, url4_url) — nested url4 URLs with text inside balanced parens."""
    node = parse(
        "(https://localhost:8000/ensemble?context=(Background:, https://wiki.internal/project-overview),"
        " https://localhost:8000/ensemble?context=(Recent changes:, https://api.github.com/repos/org/repo/commits))"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert (
        node.items[0].value
        == "https://localhost:8000/ensemble?context=(Background:, https://wiki.internal/project-overview)"
    )
    assert isinstance(node.items[1], Url4Url)
    assert (
        node.items[1].value
        == "https://localhost:8000/ensemble?context=(Recent changes:, https://api.github.com/repos/org/repo/commits)"
    )


def test_parse_strips_whitespace() -> None:
    node = parse("  hello world  ")
    assert isinstance(node, Url4Text)
    assert node.value == "hello world"


def test_parse_list_strips_item_whitespace() -> None:
    node = parse("(  http://a.com ,  hello  )")
    assert isinstance(node, Url4List)
    url_item = node.items[0]
    text_item = node.items[1]
    assert isinstance(url_item, Url4Url)
    assert url_item.value == "http://a.com"
    assert isinstance(text_item, Url4Text)
    assert text_item.value == "hello"


# ---------------------------------------------------------------------------
# Backend-call tests — /path()!<intent> form
# ---------------------------------------------------------------------------
#
# The backend_call syntax is the new shorthand for "invoke a plugin as a
# backend LLM call, with <intent> as its instruction." It parses into a
# Url4BackendCall AST node distinct from Url4RelUrl (which stays a URL fetch).
#
# Stage A (SF-79) implements only the parser-level recognition. Execution
# (Stage B) is tested separately — here we only assert AST shape.


def test_parse_backend_call_without_intent() -> None:
    node = parse("/claude()")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/claude"
    assert node.intent is None


def test_parse_backend_call_with_text_intent() -> None:
    node = parse("/claude()!hello")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/claude"
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "hello"


def test_parse_backend_call_with_relurl_intent() -> None:
    """The common frontend-substituted shape: /claude()!/data/<blob-key>."""
    node = parse("/claude()!/data/abc123")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/claude"
    assert isinstance(node.intent, Url4RelUrl)
    assert node.intent.value == "/data/abc123"


def test_parse_backend_call_with_url_intent() -> None:
    """Edge case: the intent can be an absolute URL. Not the common shape,
    but the grammar should accept it without special-casing."""
    node = parse("/claude()!https://example.com/data")
    assert isinstance(node, Url4BackendCall)
    assert isinstance(node.intent, Url4Url)
    assert node.intent.value == "https://example.com/data"


def test_parse_backend_call_with_variable_intent() -> None:
    """The $prompt variable shape. Parser treats the literal '$prompt'
    string as Url4Text — the frontend substitutes it to a /data/<key>
    reference BEFORE the parser runs on the substituted expression."""
    node = parse("/codex()!$prompt")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/codex"
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "$prompt"


def test_parse_backend_call_different_paths() -> None:
    """Parser must accept every backend path, not just /claude."""
    for path in ("/claude", "/codex", "/gemini", "/qwen", "/ollama"):
        node = parse(f"{path}()!test")
        assert isinstance(node, Url4BackendCall)
        assert node.path == path


def test_parse_backend_call_alias_path() -> None:
    """SF-346: a two-segment ``/backend/<alias>`` path parses to a single
    Url4BackendCall whose ``path`` retains both segments. The dispatcher's
    alias branch derives the alias from ``node.path`` after the exact-match
    miss, so this grammar contract must fail loudly if the backend_path rule
    ever stops accepting an interior '/' (otherwise alias specs silently
    reparse as a relative-URL fetch and never dispatch)."""
    node = parse("/huggingface/oss20b($prompt)!answer")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/huggingface/oss20b"
    assert node.packed_context == "$prompt"
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "answer"

    for path in ("/huggingface/oss20b", "/gemini/flash"):
        aliased = parse(f"{path}()!test")
        assert isinstance(aliased, Url4BackendCall)
        assert aliased.path == path


def test_parse_list_of_backend_calls_fanout_shape() -> None:
    """The target spec's fan-out shape: a parenthesized list where every
    element is a backend call to a different backend with the same intent."""
    node = parse("(/claude()!$prompt,/codex()!$prompt,/gemini()!$prompt)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 3

    for item, expected_path in zip(node.items, ["/claude", "/codex", "/gemini"], strict=True):
        assert isinstance(item, Url4BackendCall)
        assert item.path == expected_path
        assert isinstance(item.intent, Url4Text)
        assert item.intent.value == "$prompt"


def test_parse_list_of_backend_calls_different_intents() -> None:
    """Each element of a fan-out list can have its own distinct intent.
    This shape is used for deterministic manual testing and e2e tests
    that want to assert the reducer received three specific responses."""
    node = parse("(/claude()!hello, /claude()!world, /claude()!again)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    intents = [item.intent.value for item in node.items]  # type: ignore[union-attr]
    assert intents == ["hello", "world", "again"]


def test_parse_backend_call_does_not_shadow_regular_relurl() -> None:
    """Regression: /claude (no parens) must still parse as a Url4RelUrl,
    not as a Url4BackendCall. The backend_call alternative only matches
    when () is present immediately after the path."""
    node = parse("/claude")
    assert isinstance(node, Url4RelUrl)
    assert node.value == "/claude"


def test_parse_backend_call_does_not_shadow_querystring_relurl() -> None:
    """Regression: /claude?q=... still parses as a Url4RelUrl (URL fetch),
    not as a backend call — there are no () after the path."""
    node = parse("/claude?q=(https://ex.com)!summarize")
    assert isinstance(node, Url4RelUrl)
    assert node.value == "/claude?q=(https://ex.com)!summarize"


def test_parse_mixed_list_backend_call_and_fetch() -> None:
    """A list can contain both backend calls and plain URL fetches.
    This isn't a common shape but the grammar shouldn't reject it."""
    node = parse("(/claude()!hi, /data/abc, https://example.com)")
    assert isinstance(node, Url4List)
    assert isinstance(node.items[0], Url4BackendCall)
    assert isinstance(node.items[1], Url4RelUrl)
    assert isinstance(node.items[2], Url4Url)


# ---------------------------------------------------------------------------
# SF-89: Context packing — /backend('context')!intent
# ---------------------------------------------------------------------------


def test_parse_context_packing_text() -> None:
    """The target form from Kevin's spec: /claude('prompt text')!intent."""
    node = parse("/claude(What is quantum computing?)!Explain clearly")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/claude"
    assert node.packed_context == "What is quantum computing?"
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "Explain clearly"


def test_parse_context_packing_with_data_ref() -> None:
    """Context can be a /data/<key> reference — common after precompilation."""
    node = parse("/claude(/data/abc123)!Explain")
    assert isinstance(node, Url4BackendCall)
    assert node.packed_context == "/data/abc123"


def test_parse_context_packing_empty_parens_no_context() -> None:
    """Empty parens: packed_context should be None (backward compat)."""
    node = parse("/claude()!hello")
    assert isinstance(node, Url4BackendCall)
    assert node.packed_context is None
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "hello"


def test_parse_context_packing_no_intent() -> None:
    """Context without intent — just /claude('text') with no ! afterward."""
    node = parse("/claude(some context)")
    assert isinstance(node, Url4BackendCall)
    assert node.packed_context == "some context"
    assert node.intent is None


def test_parse_context_packing_in_fanout_list() -> None:
    """Kevin's weighted ensemble form (without weights — those are SF-88).
    Each element has context packing."""
    node = parse(
        "(/claude(What is quantum computing?)!Explain,"
        "/codex(What is quantum computing?)!Explain,"
        "/gemini(What is quantum computing?)!Explain)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    for item in node.items:
        assert isinstance(item, Url4BackendCall)
        assert item.packed_context == "What is quantum computing?"
        assert isinstance(item.intent, Url4Text)
        assert item.intent.value == "Explain"


def test_parse_context_packing_with_special_chars() -> None:
    """Context can contain bangs, slashes, commas (since the regex
    matches everything except parens inside the backend_context)."""
    node = parse("/claude(What is 2+2? answer: 4, right!)!confirm")
    assert isinstance(node, Url4BackendCall)
    assert "2+2" in node.packed_context
    assert "answer: 4, right!" in node.packed_context


# ---------------------------------------------------------------------------
# SF-88: Named + weighted source labels
# ---------------------------------------------------------------------------


def test_parse_named_weighted_backend_call() -> None:
    """Kevin's form: claude:40:/claude(prompt)!intent."""
    node = parse("claude:40:/claude(quantum)!explain")
    assert isinstance(node, Url4BackendCall)
    assert node.name == "claude"
    assert node.weight == 40.0
    assert node.path == "/claude"
    assert node.packed_context == "quantum"
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "explain"


def test_parse_named_weighted_decimal_weight() -> None:
    """Weight can be a decimal."""
    node = parse("alpha:0.5:/claude()!hi")
    assert isinstance(node, Url4BackendCall)
    assert node.name == "alpha"
    assert node.weight == 0.5


def test_parse_named_weighted_no_context() -> None:
    """Named + weighted with empty parens."""
    node = parse("codex:30:/codex()!answer")
    assert isinstance(node, Url4BackendCall)
    assert node.name == "codex"
    assert node.weight == 30.0
    assert node.path == "/codex"
    assert node.packed_context is None


def test_parse_named_weighted_fanout_list() -> None:
    """Kevin's full weighted ensemble expression."""
    node = parse(
        "(claude:40:/claude(quantum)!explain,"
        "codex:30:/codex(quantum)!explain,"
        "gemini:30:/gemini(quantum)!explain)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3

    names_weights = [(i.name, i.weight) for i in node.items]
    assert names_weights == [("claude", 40.0), ("codex", 30.0), ("gemini", 30.0)]
    assert [i.path for i in node.items] == ["/claude", "/codex", "/gemini"]


def test_parse_unnamed_backend_call_has_none_name_weight() -> None:
    """Backward compat: /claude()!hello without name:weight: prefix."""
    node = parse("/claude()!hello")
    assert isinstance(node, Url4BackendCall)
    assert node.name is None
    assert node.weight is None


def test_parse_name_only_without_weight_not_valid() -> None:
    """name: without weight: is not the label syntax — it should fall
    through to text or be part of a different parse. The grammar requires
    name:weight: (both parts).

    'alpha:/claude()!hi' — 'alpha:' doesn't match source_label because
    the weight regex isn't satisfied, so the parser tries other alternatives.
    """
    # This should NOT parse as a named backend_call. It may parse as
    # text or fail depending on grammar alternatives. We don't require
    # a specific behavior, just that name is NOT set.
    try:
        node = parse("alpha:/claude()!hi")
        if isinstance(node, Url4BackendCall):
            assert node.name is None  # label didn't match
    except Exception:
        pass  # parse failure is also acceptable


# ---------------------------------------------------------------------------
# SF-89: Context packing — dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_resolve_context_packing_passes_sources_to_plugin() -> None:
    """When /claude('context')!intent dispatches, the plugin receives
    sources='context' AND intent='intent' — not just intent."""
    plugin = _FakeDispatchPlugin(name="claude-api", paths=["/claude"], response="ok")
    app = _FakeApp(_FakePluginRegistry({"claude-api": plugin}))
    node = Url4BackendCall(
        path="/claude",
        packed_context="What is quantum computing?",
        intent=Url4Text(value="Explain clearly"),
    )

    await resolve(node, app=app)

    assert len(plugin.calls) == 1
    intent, sources, _ = plugin.calls[0]
    assert intent == "Explain clearly"
    assert sources == "What is quantum computing?"


@pytest.mark.anyio
async def test_resolve_context_packing_empty_context_passes_empty_sources() -> None:
    """Empty parens /claude()!intent passes sources='' (backward compat)."""
    plugin = _FakeDispatchPlugin(name="claude-api", paths=["/claude"], response="ok")
    app = _FakeApp(_FakePluginRegistry({"claude-api": plugin}))
    node = Url4BackendCall(path="/claude", packed_context=None, intent=Url4Text(value="hello"))

    await resolve(node, app=app)

    _, sources, _ = plugin.calls[0]
    assert sources == ""


@pytest.mark.anyio
async def test_resolve_context_packing_no_intent_passes_empty_intent() -> None:
    """Just /claude('context') with no intent → intent='' sources='context'."""
    plugin = _FakeDispatchPlugin(name="claude-api", paths=["/claude"], response="ok")
    app = _FakeApp(_FakePluginRegistry({"claude-api": plugin}))
    node = Url4BackendCall(path="/claude", packed_context="some context", intent=None)

    await resolve(node, app=app)

    intent, sources, _ = plugin.calls[0]
    assert intent == ""
    assert sources == "some context"


# ---------------------------------------------------------------------------
# Backend-call resolver tests — Stage B dispatch
# ---------------------------------------------------------------------------
#
# Stage B wires Url4BackendCall resolution through the active plugin
# registry. The resolver walks ``app.state.plugins.active_plugins`` looking
# for one whose ``backend_call_paths`` contains the target path and calls
# its ``handle_backend_call`` method.
#
# These tests use a minimal fake plugin registry so they don't need the
# real FastAPI + llm-base stack.


class _FakePluginRegistry:
    """Minimal stand-in for screamingface.core.registry.PluginRegistry.

    Only implements the attribute the resolver touches: active_plugins is
    a dict of name → plugin-like object.
    """

    def __init__(self, active: dict) -> None:
        self.active_plugins = active


class _FakeAppState:
    def __init__(self, plugins: _FakePluginRegistry) -> None:
        self.plugins = plugins


class _FakeApp:
    def __init__(self, plugins: _FakePluginRegistry) -> None:
        self.state = _FakeAppState(plugins)


class _FakeDispatchPlugin:
    """Minimal plugin stub with the two attributes the resolver inspects."""

    def __init__(self, name: str, paths: list[str], response: str) -> None:
        self.name = name
        self.backend_call_paths = paths
        self._response = response
        self.calls: list[tuple[str, str, object]] = []

    async def handle_backend_call(self, intent: str, *, sources: str = "", app, env=None) -> str:
        del env
        self.calls.append((intent, sources, app))
        return self._response


@pytest.mark.anyio
async def test_resolve_backend_call_dispatches_to_matching_plugin() -> None:
    plugin = _FakeDispatchPlugin(name="claude-backend-api", paths=["/claude"], response="Four")
    app = _FakeApp(_FakePluginRegistry({"claude-backend-api": plugin}))
    node = Url4BackendCall(path="/claude", intent=Url4Text(value="What is 2+2?"))

    result = await resolve(node, app=app)

    assert result == "Four"
    assert plugin.calls == [("What is 2+2?", "", app)]


@pytest.mark.anyio
async def test_resolve_backend_call_flattens_relurl_intent() -> None:
    """When the intent is a Url4RelUrl, the resolver fetches it first
    (via in-process ASGI) and hands the body to the plugin as a string.
    That's how $prompt substitution works: /claude()!/data/<key> becomes
    'whatever is in the blob' as the intent string."""
    plugin = _FakeDispatchPlugin(name="claude-backend-api", paths=["/claude"], response="ok")
    app = _FakeApp(_FakePluginRegistry({"claude-backend-api": plugin}))
    node = Url4BackendCall(path="/claude", intent=Url4RelUrl(value="/data/abc"))

    with patch(
        "screamingface.plugins.url4_executor.url4_resolve._fetch_relative",
        new_callable=AsyncMock,
        return_value="user's question from the blob",
    ):
        await resolve(node, app=app)

    assert plugin.calls == [("user's question from the blob", "", app)]


@pytest.mark.anyio
async def test_resolve_backend_call_empty_intent_is_empty_string() -> None:
    plugin = _FakeDispatchPlugin(name="claude-backend-api", paths=["/claude"], response="ok")
    app = _FakeApp(_FakePluginRegistry({"claude-backend-api": plugin}))
    node = Url4BackendCall(path="/claude", intent=None)

    await resolve(node, app=app)

    assert plugin.calls == [("", "", app)]


@pytest.mark.anyio
async def test_resolve_backend_call_no_app_raises() -> None:
    node = Url4BackendCall(path="/claude", intent=Url4Text(value="hi"))
    with pytest.raises(RuntimeError, match="without an app context"):
        await resolve(node, app=None)


@pytest.mark.anyio
async def test_resolve_backend_call_no_matching_plugin_raises() -> None:
    app = _FakeApp(_FakePluginRegistry({}))
    node = Url4BackendCall(path="/claude", intent=Url4Text(value="hi"))

    with pytest.raises(RuntimeError, match="No active plugin handles"):
        await resolve(node, app=app)


@pytest.mark.anyio
async def test_resolve_backend_call_error_lists_known_paths() -> None:
    """Error message includes the set of known backend_call_paths from
    active plugins so the user can see what IS available."""
    other_plugin = _FakeDispatchPlugin(name="other", paths=["/codex", "/gemini"], response="x")
    app = _FakeApp(_FakePluginRegistry({"other": other_plugin}))
    node = Url4BackendCall(path="/claude", intent=Url4Text(value="hi"))

    with pytest.raises(RuntimeError, match="/codex") as exc_info:
        await resolve(node, app=app)
    assert "/gemini" in str(exc_info.value)


@pytest.mark.anyio
async def test_resolve_list_with_backend_call_dispatches() -> None:
    """A list mixing plain text and backend calls resolves each element
    through its appropriate path. Proves fan-out across N backend calls
    works — this is the foundation the ensemble reducer builds on."""
    plugin = _FakeDispatchPlugin(name="claude-backend-api", paths=["/claude"], response="LLM reply")
    app = _FakeApp(_FakePluginRegistry({"claude-backend-api": plugin}))
    node = Url4List(
        items=(
            Url4Text(value="plain text"),
            Url4BackendCall(path="/claude", intent=Url4Text(value="hi")),
            Url4BackendCall(path="/claude", intent=Url4Text(value="bye")),
        )
    )

    result = await resolve(node, app=app)

    # Results joined with newlines (standard Url4List resolver behavior)
    assert result == "plain text\nLLM reply\nLLM reply"
    # Both backend calls dispatched in order
    assert plugin.calls == [("hi", "", app), ("bye", "", app)]


@pytest.mark.anyio
async def test_resolve_fanout_list_of_three_backend_calls() -> None:
    """The target ensemble fan-out shape. Three backend calls to the
    same backend, collected in order. This is the Stage B foundation
    that Stage C's ensemble executor builds fan-out-reduce on top of."""
    plugin = _FakeDispatchPlugin(name="claude-backend-api", paths=["/claude"], response="response")
    app = _FakeApp(_FakePluginRegistry({"claude-backend-api": plugin}))
    node = parse("(/claude()!a, /claude()!b, /claude()!c)")

    result = await resolve(node, app=app)

    assert result == "response\nresponse\nresponse"
    assert [call[0] for call in plugin.calls] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Resolver tests (async — mock _fetch_url)
# ---------------------------------------------------------------------------

PATCH_TARGET = "screamingface.plugins.url4_executor.url4_resolve._fetch_url"


@pytest.mark.anyio
async def test_resolve_text_node() -> None:
    node = Url4Text(value="hello world")
    result = await resolve(node)
    assert result == "hello world"


@pytest.mark.anyio
async def test_resolve_url_node() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="fetched content"):
        node = Url4Url(value="http://example.com/data")
        result = await resolve(node)
        assert result == "fetched content"


@pytest.mark.anyio
async def test_resolve_list_node() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="from url"):
        node = Url4List(
            items=(
                Url4Url(value="http://example.com"),
                Url4Text(value="raw text here"),
            )
        )
        result = await resolve(node)
        assert result == "from url\nraw text here"


@pytest.mark.anyio
async def test_resolve_nested_list() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="fetched"):
        node = Url4List(
            items=(
                Url4Text(value="hello"),
                Url4List(
                    items=(
                        Url4Url(value="http://a.com"),
                        Url4Text(value="world"),
                    )
                ),
            )
        )
        result = await resolve(node)
        assert result == "hello\nfetched\nworld"


@pytest.mark.anyio
async def test_resolve_str_plain_string() -> None:
    result = await resolve_str("hello world")
    assert result == "hello world"


@pytest.mark.anyio
async def test_resolve_str_url() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="fetched content"):
        result = await resolve_str("http://example.com/data")
        assert result == "fetched content"


@pytest.mark.anyio
async def test_resolve_str_list_mixed() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="from url"):
        result = await resolve_str("(http://example.com, raw text here)")
        assert result == "from url\nraw text here"


@pytest.mark.anyio
async def test_resolve_str_example_4() -> None:
    """Nested url4 URLs resolve as single URL fetches."""
    responses = {
        "https://localhost:8000/ensemble?context="
        "(https://docs.a.com, https://docs.b.com)": "content-ab",
        "https://localhost:8000/ensemble?context="
        "(https://docs.c.com, https://docs.d.com)": "content-cd",
    }

    async def mock_fetch(url: str) -> str:
        return responses[url]

    with patch(PATCH_TARGET, side_effect=mock_fetch):
        result = await resolve_str(
            "(https://localhost:8000/ensemble?context=(https://docs.a.com, https://docs.b.com),"
            " https://localhost:8000/ensemble?context=(https://docs.c.com, https://docs.d.com))"
        )
        assert result == "content-ab\ncontent-cd"


@pytest.mark.anyio
async def test_resolve_str_example_10() -> None:
    """Nested url4 URLs with text inside balanced parens resolve correctly."""
    responses = {
        "https://localhost:8000/ensemble?context="
        "(Background:, https://wiki.internal/project-overview)": "bg-content",
        "https://localhost:8000/ensemble?context="
        "(Recent changes:, https://api.github.com/repos/org/repo/commits)": "changes-content",
    }

    async def mock_fetch(url: str) -> str:
        return responses[url]

    with patch(PATCH_TARGET, side_effect=mock_fetch):
        result = await resolve_str(
            "(https://localhost:8000/ensemble?context=(Background:, https://wiki.internal/project-overview),"
            " https://localhost:8000/ensemble?context=(Recent changes:, https://api.github.com/repos/org/repo/commits))"
        )
        assert result == "bg-content\nchanges-content"


# ---------------------------------------------------------------------------
# SF-92: Source expansion — *source
# ---------------------------------------------------------------------------


def test_parse_expanded_source_url() -> None:
    """*https://... parses as Url4ExpandedSource with inner Url4Url."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    node = parse("*https://example.com/data.jsonl")
    assert isinstance(node, Url4ExpandedSource)
    assert isinstance(node.inner, Url4Url)
    assert node.inner.value == "https://example.com/data.jsonl"


def test_parse_expanded_source_relurl() -> None:
    """*/data/<key> parses as expanded source with inner relurl."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    node = parse("*/data/abc123")
    assert isinstance(node, Url4ExpandedSource)
    assert isinstance(node.inner, Url4RelUrl)
    assert node.inner.value == "/data/abc123"


def test_parse_expanded_source_in_group() -> None:
    """(*source) inside a group — the common form."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    node = parse("(*https://example.com/data.jsonl)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 1
    assert isinstance(node.items[0], Url4ExpandedSource)


def test_parse_expanded_source_mixed_with_regular() -> None:
    """(*source, regular_text) — expansion + regular source in same group."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    node = parse("(*https://example.com/data.jsonl, hello)")
    assert isinstance(node, Url4List)
    assert isinstance(node.items[0], Url4ExpandedSource)
    assert isinstance(node.items[1], Url4Text)


@pytest.mark.anyio
async def test_resolve_expanded_source_jsonl() -> None:
    """*source fetches the URL, parses as JSONL, joins items."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    jsonl_body = '{"q":"What is 2+2?"}\n{"q":"Capital?"}\n{"q":"Color?"}'

    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value=jsonl_body):
        node = Url4ExpandedSource(inner=Url4Url(value="https://example.com/data.jsonl"))
        result = await resolve(node)

    lines = result.split("\n")
    assert len(lines) == 3
    assert "2+2" in lines[0]
    assert "Capital" in lines[1]


@pytest.mark.anyio
async def test_resolve_expanded_source_json_array() -> None:
    """*source with a JSON array body."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    json_body = '["alpha", "beta", "gamma"]'

    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value=json_body):
        node = Url4ExpandedSource(inner=Url4Url(value="https://example.com/data.json"))
        result = await resolve(node)

    assert result == "alpha\nbeta\ngamma"


@pytest.mark.anyio
async def test_resolve_expanded_source_empty_collection() -> None:
    """*source with an empty collection body → empty string."""
    from screamingface.plugins.url4_executor.url4 import Url4ExpandedSource

    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="[]"):
        node = Url4ExpandedSource(inner=Url4Url(value="https://example.com/empty.json"))
        result = await resolve(node)

    assert result == ""
