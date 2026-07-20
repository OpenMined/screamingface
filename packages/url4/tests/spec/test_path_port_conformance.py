"""`OME-507` cycle 2 — `path` / `segment` / `port` character classes.

# FEATURE: the parser accepts the path and port shapes the grammar defines.
#
#   path         = segment *( "/" segment )
#   segment      = *( ALPHA / DIGIT / "-" / "_" / "." / "~" )      <- expressions
#   path-segment = 1*( ALPHA / DIGIT / "-" / "_" / "." / "~"
#                    / ":" / "@" / "!" / "$" / "&" / "+" / "=" )   <- data URIs
#   port         = 1*DIGIT
#
# WHY this was asymmetric before: `render._check_path` ALREADY enforced the
# narrow `segment` charset on output, so `/foo$bar(x)!y` parsed but could not
# re-render — a value that round-trips nowhere. Both sides now read one pattern.
#
# INVARIANT: the two path charsets are DIFFERENT productions. An expression's
# path is narrow; a `relative-uri` data path is wide (it admits `$`, which is
# what makes `/data/$topic` a legal data reference). Narrowing the data form to
# match would break variable-bearing paths.
"""

from __future__ import annotations

import pytest

from url4.errors import ParseError
from url4.grammar import parse
from url4.nodes import RelExpr, RelUrl, RemoteExpr

# --- expression paths take the NARROW `segment` charset -------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "/foo$bar(x)!'y'",  # "$" is not in `segment`
        "/foo bar(x)!'y'",  # space
        "/foo@bar(x)!'y'",  # "@"
        "/foo!bar(x)!'y'",  # "!"
        "/foo%2Fbar(x)!'y'",  # "%"
        "/a/b$c?q=(x)!'y'",  # canonical form, same rule
    ],
)
def test_illegal_expression_path_is_rejected(text: str) -> None:
    with pytest.raises(ParseError, match="path"):
        parse(text)


@pytest.mark.parametrize(
    "text",
    ["/claude(x)!'y'", "/a/b/c(x)!'y'", "/v1.2(x)!'y'", "/a-b_c~d(x)!'y'", "/a?t=1&q=(x)!'y'"],
)
def test_legal_expression_path_still_parses(text: str) -> None:
    assert isinstance(parse(text), RelExpr)


def test_remote_expression_path_takes_the_same_charset() -> None:
    with pytest.raises(ParseError, match="path"):
        parse("url4://node.ai/v1$x(a)!'y'")
    assert isinstance(parse("url4://node.ai/v1(a)!'y'"), RemoteExpr)


# --- `relative-uri` data paths keep the WIDE `path-segment` charset --------------------


@pytest.mark.parametrize(
    "text",
    [
        "/data/$topic",  # "$" — the variable-bearing data path
        "/api/patient/42",
        "/a:b/c@d",
        "/a+b/c=d",
        "/api/search?q=hello&limit=10",  # the query-tail is not narrowed
    ],
)
def test_legal_data_path_still_parses(text: str) -> None:
    assert isinstance(parse(text), RelUrl)


@pytest.mark.parametrize("text", ["/api/a b", "/api/a\tb"])
def test_illegal_data_path_is_rejected(text: str) -> None:
    with pytest.raises(ParseError, match="path"):
        parse(text)


# --- port = 1*DIGIT --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["url4://host:not_a_port/p(x)!'y'", "url4://host:80a/p(x)!'y'", "url4://host:/p(x)!'y'"],
)
def test_non_numeric_port_is_rejected(text: str) -> None:
    with pytest.raises(ParseError, match="port"):
        parse(text)


@pytest.mark.parametrize("text", ["url4://host:8080/p(x)!'y'", "url4://host/p(x)!'y'"])
def test_legal_authority_still_parses(text: str) -> None:
    assert isinstance(parse(text), RemoteExpr)


def test_host_itself_is_not_charset_checked() -> None:
    # INVARIANT: `host = hostname / IPv4address`, and the grammar defines
    # NEITHER `hostname` nor `IPv4address`. Inventing a charset here would be
    # asserting a rule the spec does not state, so only the port is checked.
    assert isinstance(parse("url4://weird_host.example/p(x)!'y'"), RemoteExpr)


# --- parse and render now agree ---------------------------------------------------------


def test_parse_and_render_agree_on_the_expression_path_charset() -> None:
    # The asymmetry this cycle closes: anything that parses must re-render.
    from url4.render import render

    node = parse("/a-b_c.d~e/f(x)!'y'")
    assert isinstance(node, RelExpr)
    assert render(node) == "/a-b_c.d~e/f(x)!'y'"
