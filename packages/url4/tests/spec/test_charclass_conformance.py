"""`OME-504` — the ABNF's character classes, enforced.

# FEATURE: the parser accepts exactly the language the grammar defines — no more.
#
# WHY these were all one-directional: the parser validated STRUCTURE (colon and
# semicolon boundaries) but never CHARACTER CLASSES, and several identifier
# patterns used Python's `\\w`, which is Unicode-aware where the ABNF means ASCII
# `ALPHA`. Nothing here was producing wrong behaviour — the parser was a strict
# superset. This is hardening.
#
# AIDEV-NOTE: `bare-value` and the non-ASCII bound on `quoted-text` are
# DELIBERATELY NOT tightened — see the `no natural language was harmed` section at
# the bottom. The ABNF is under-specified for NL content there (`OME-503`), and
# tightening it would break url4's actual purpose: carrying prompts.
"""

from __future__ import annotations

import pytest

from url4.errors import ParseError
from url4.grammar import parse, parse_value
from url4.nodes import Binding, IdentityRef, Text, VarRef

# --- ASCII anchoring: `\w` is Unicode-aware, ABNF `ALPHA` is not --------------------


def test_unicode_identifier_is_not_a_variable_ref() -> None:
    # `$café` is not a valid variable-ref (name-part is ASCII), so it degrades to
    # bare text rather than becoming a VarRef with a Unicode name.
    assert isinstance(parse_value("$café"), Text)


def test_ascii_variable_ref_still_parses() -> None:
    assert isinstance(parse_value("$cafe"), VarRef)


def test_unicode_binding_name_does_not_bind() -> None:
    # `name-part` is ASCII, so `articleé=` is NOT the `name=value` sugar form. It
    # degrades to a bare value rather than raising — bare-value is deliberately
    # untightened (Tier-3 exclusion), so this is the correct outcome: the Unicode
    # name simply never becomes an identifier.
    node = parse("articleé=https://x.com")
    assert not isinstance(node, Binding)


# --- identity-name = name-part / 1*DIGIT --------------------------------------------


@pytest.mark.parametrize("token", ["@9lives", "@1a", "@7up"])
def test_digit_led_identity_name_is_rejected(token: str) -> None:
    # ABNF: `identity-name = name-part / 1*DIGIT`. A digit-led name followed by
    # letters is neither alternative.
    with pytest.raises(ParseError):
        parse_value(token)


@pytest.mark.parametrize("token", ["@alice", "@_bob", "@123", "@a1"])
def test_legal_identity_names_still_parse(token: str) -> None:
    assert isinstance(parse_value(token), IdentityRef)


# --- identity-collection = 1*( "/" path-segment ) -----------------------------------


@pytest.mark.parametrize("token", ["@alice/dr,afts", "@bob/note#s", "@carol/a(b)"])
def test_illegal_identity_collection_segment_is_rejected(token: str) -> None:
    with pytest.raises(ParseError):
        parse_value(token)


def test_legal_multi_segment_identity_collection_parses() -> None:
    node = parse_value("@alice/drafts/2026")
    assert isinstance(node, IdentityRef)
    assert node.collection == "drafts/2026"


# --- budget-key = 1*( ALPHA / "_" ) — no digits -------------------------------------


@pytest.mark.parametrize("token", ["name:budget1=5:src=x", "name:b2=5:src=x"])
def test_budget_key_with_digits_is_rejected(token: str) -> None:
    with pytest.raises(ParseError):
        parse(token)


def test_legal_budget_key_still_parses() -> None:
    assert parse("name:budget=5:src=https://x") is not None


# --- scalar-budget-value = 1*( ALPHA / DIGIT / "." / "-" / "_" ) --------------------


@pytest.mark.parametrize(
    "token",
    ["name:budget=foo bar:src=https://x", "name:budget=foo@baz:src=https://x"],
)
def test_illegal_scalar_budget_value_is_rejected(token: str) -> None:
    with pytest.raises(ParseError):
        parse(token)


# --- exec-key / exec-value charsets --------------------------------------------------


@pytest.mark.parametrize("token", ["https://x;mode2=foo", "https://x;m0de=foo"])
def test_exec_key_with_digits_is_rejected(token: str) -> None:
    # ABNF extensible form: `1*( ALPHA / "_" / "." )` — no digits.
    with pytest.raises(ParseError):
        parse(token)


@pytest.mark.parametrize("token", ["https://x;mode=foo@bar", "https://x;mode=foo bar"])
def test_illegal_exec_value_is_rejected(token: str) -> None:
    with pytest.raises(ParseError):
        parse(token)


def test_iteration_slice_colon_is_legal_exec_value() -> None:
    # PRE-APPLIES `OME-503` amendment A1: the ABNF omits ":" from exec-value, but
    # `;iteration.slice=1:3` is spec-documented, implemented, and covered by the
    # passing prior test `test_slice_parses`. The grammar is wrong, not the code.
    assert parse("https://x;iteration.slice=1:3") is not None


# --- coord-key is a CLOSED enum ------------------------------------------------------


@pytest.mark.parametrize("token", ["https://x;coord.bogus=3", "https://x;coord.nope=1"])
def test_unknown_coord_key_is_rejected(token: str) -> None:
    with pytest.raises(ParseError):
        parse(token)


@pytest.mark.parametrize(
    "token",
    [
        "https://x;coord.rounds=3",
        "https://x;coord.max_turns=5",
        "https://x;coord.convergence=high",
        "https://x;coord.turn_timeout=30",
    ],
)
def test_declared_coord_keys_still_parse(token: str) -> None:
    assert parse(token) is not None


# --- structured-weight is FLAT (nesting belongs to structured-budget-value) ----------


@pytest.mark.parametrize(
    "token",
    ["name:(scope:(domain:5)):src=https://x", "name:weight=(scope:(domain:5)):src=https://x"],
)
def test_nested_structured_weight_is_rejected(token: str) -> None:
    # `structured-weight = "(" struct-pair *("," struct-pair) ")"` — struct-val is
    # terminal. Only `structured-budget-value` may nest (and only two deep).
    with pytest.raises(ParseError):
        parse(token)


def test_flat_structured_weight_still_parses() -> None:
    assert parse("name:(medical:0.9,legal:0.5):src=https://x") is not None


def test_two_level_structured_budget_still_parses() -> None:
    # The depth-2 budget nesting the audit confirmed CORRECT must survive.
    assert parse("name:budget=(scope:(domain:5)):src=https://x") is not None


# --- quoted-char: escapes are only \' and \\; no raw control characters -------------


@pytest.mark.parametrize("token", ["'a\\nb'", "'a\\qb'"])
def test_undefined_backslash_escape_is_rejected(token: str) -> None:
    with pytest.raises(ParseError):
        parse_value(token)


def test_raw_control_character_in_quotes_is_rejected() -> None:
    with pytest.raises(ParseError):
        parse_value("'a\tb'")


@pytest.mark.parametrize("token", [r"'it\'s'", r"'back\\slash'"])
def test_defined_escapes_still_parse(token: str) -> None:
    assert isinstance(parse_value(token), Text)


# --- no natural language was harmed --------------------------------------------------
#
# INVARIANT: these are the Tier-3 exclusions. url4 carries natural-language prompts;
# a grammar that rejects them is useless for its purpose. `OME-503` amends the ABNF
# here rather than the code being tightened to match it.


@pytest.mark.parametrize(
    "token",
    [
        "'a b c'",
        "'héllo 世界 🎉'",
        "'Summarize $article in $style tone'",
        "'punctuation! and? more.'",
    ],
)
def test_natural_language_quoted_text_still_parses(token: str) -> None:
    assert isinstance(parse_value(token), Text)


@pytest.mark.parametrize("token", ["hello!world", "a b c", "a<b>c"])
def test_natural_language_bare_values_still_parse(token: str) -> None:
    assert parse_value(token) is not None
