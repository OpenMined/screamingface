"""Grammar-level parsing: each detection rule maps to the right AST node."""

from __future__ import annotations

import pytest

from url4.errors import ParseError
from url4.grammar import parse
from url4.nodes import (
    Binding,
    Expression,
    RelExpr,
    RelUrl,
    Source,
    Text,
    Url,
)


def test_absolute_url() -> None:
    assert parse("https://example.com/a") == Url("https://example.com/a")


def test_relative_url() -> None:
    assert parse("/api/data") == RelUrl("/api/data")


def test_bare_text() -> None:
    assert parse("hello world") == Text("hello world")


def test_quoted_text_strips_quotes() -> None:
    # Quotes are delimiters (spec §5.1); content is what is inside.
    assert parse("'formal'") == Text("formal")


def test_group_of_sources() -> None:
    node = parse("(a, https://x)")
    assert node == Expression(sources=(Text("a"), Url("https://x")), intent=None)


def test_named_binding() -> None:
    assert parse("article=https://x") == Binding("article", Url("https://x"), "=")


def test_relative_expression_with_context_and_intent() -> None:
    node = parse("/claude(ctx)!answer this")
    assert node == RelExpr(path="/claude", context="ctx", intent=Text("answer this"))


def test_weighted_relative_expression() -> None:
    # The name:weight: label is the two-axis descriptor (§4.3) — it wraps ANY
    # value in a Source, not just relative expressions.
    node = parse("claude:0.6:/claude(x)!go")
    assert node == Source(
        value=RelExpr(path="/claude", context="x", intent=Text("go")),
        name="claude",
        weight=0.6,
    )


def test_expansion_prefix_source() -> None:
    # §5.2 rule 9: a source-initial '*' marks the source for expansion.
    node = parse("*https://data.com/rows")
    assert node == Source(value=Url("https://data.com/rows"), expand=True)


def test_star_not_before_paren_is_literal_mid_value() -> None:
    # §5.3.3: mid-value '*' is structural ONLY when immediately followed by '('.
    assert parse("s3://bucket/prefix/*") == Url("s3://bucket/prefix/*")


def test_grouped_reduce_binding() -> None:
    node = parse("consensus=(a, b)!merge")
    assert node == Binding(
        "consensus",
        Expression(sources=(Text("a"), Text("b")), intent=Text("merge")),
        "=",
    )


def test_malformed_raises_parse_error() -> None:
    with pytest.raises(ParseError) as exc_info:
        parse("(unclosed")
    assert exc_info.value.code == "malformed_source"
