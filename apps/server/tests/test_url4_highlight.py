"""Tests for the url4 syntax-highlight tokenizer."""

from __future__ import annotations

from screamingface.plugins.url4_executor.highlight import tokenize


def test_plain_text() -> None:
    tokens = tokenize("hello world")
    assert tokens == [{"type": "text", "value": "hello world", "depth": 0}]


def test_single_url() -> None:
    tokens = tokenize("https://example.com/api")
    assert tokens == [{"type": "url", "value": "https://example.com/api", "depth": 0}]


def test_simple_list() -> None:
    tokens = tokenize("(http://a.com, hello)")
    assert tokens == [
        {"type": "paren", "value": "(", "depth": 0},
        {"type": "url", "value": "http://a.com", "depth": 1},
        {"type": "comma", "value": ",", "depth": 1},
        {"type": "ws", "value": " ", "depth": 1},
        {"type": "text", "value": "hello", "depth": 1},
        {"type": "paren", "value": ")", "depth": 0},
    ]


def test_nested_list() -> None:
    tokens = tokenize("(http://a.com, (http://b.com, inner))")
    assert tokens == [
        {"type": "paren", "value": "(", "depth": 0},
        {"type": "url", "value": "http://a.com", "depth": 1},
        {"type": "comma", "value": ",", "depth": 1},
        {"type": "ws", "value": " ", "depth": 1},
        {"type": "paren", "value": "(", "depth": 1},
        {"type": "url", "value": "http://b.com", "depth": 2},
        {"type": "comma", "value": ",", "depth": 2},
        {"type": "ws", "value": " ", "depth": 2},
        {"type": "text", "value": "inner", "depth": 2},
        {"type": "paren", "value": ")", "depth": 1},
        {"type": "paren", "value": ")", "depth": 0},
    ]


def test_intent_suffix() -> None:
    tokens = tokenize("(http://docs.com, context)!summarize")
    assert tokens == [
        {"type": "paren", "value": "(", "depth": 0},
        {"type": "url", "value": "http://docs.com", "depth": 1},
        {"type": "comma", "value": ",", "depth": 1},
        {"type": "ws", "value": " ", "depth": 1},
        {"type": "text", "value": "context", "depth": 1},
        {"type": "paren", "value": ")", "depth": 0},
        {"type": "intent_sep", "value": "!", "depth": 0},
        {"type": "intent", "value": "summarize", "depth": 0},
    ]


def test_whitespace_stripped() -> None:
    """Parser strips leading/trailing whitespace from atoms."""
    tokens = tokenize("  hello world  ")
    assert tokens == [{"type": "text", "value": "hello world", "depth": 0}]


def test_three_items() -> None:
    tokens = tokenize("(http://a.com, some text, http://b.com)")
    types = [t["type"] for t in tokens]
    assert types == ["paren", "url", "comma", "ws", "text", "comma", "ws", "url", "paren"]


def test_no_intent() -> None:
    """Expression without intent produces no intent tokens."""
    tokens = tokenize("hello")
    assert all(t["type"] not in ("intent_sep", "intent") for t in tokens)


def test_intent_only_url() -> None:
    tokens = tokenize("https://example.com!do-thing")
    assert tokens == [
        {"type": "url", "value": "https://example.com", "depth": 0},
        {"type": "intent_sep", "value": "!", "depth": 0},
        {"type": "intent", "value": "do-thing", "depth": 0},
    ]
