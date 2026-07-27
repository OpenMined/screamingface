"""Spec §4.1.1 — structured annotation values (weights, budgets) and the
first-entry classifier with its no-backtrack commitment (§4.1.1.4)."""

from __future__ import annotations

import pytest

from url4.core.errors import ParseError
from url4.core.grammar import parse
from url4.core.nodes import Binding, Expression, Text, Url

# --- §4.1.1.3 four-way weight equivalence -------------------------------------


def test_scalar_weight_and_weight_keyed_are_equal() -> None:
    # §4.1.1.3 rows 1–2
    assert parse("claude:0.5:https://x") == parse("claude:weight=0.5:https://x")


def test_structured_weight_and_weight_keyed_structured_are_equal() -> None:
    # §4.1.1.3 rows 3–4
    assert parse("claude:(_default:0.5):https://x") == parse(
        "claude:weight=(_default:0.5):https://x"
    )


def test_bare_structured_weight_shape() -> None:
    # §4.1.1.3 row 3 — structured weight parses to a mapping
    from url4.core.nodes import Source

    node = parse("claude:(_default:0.5):https://x")
    assert isinstance(node, Source)
    assert node.weight == {"_default": 0.5}


# --- §4.1.1.2 structured weights and budgets ----------------------------------


def test_domain_conditional_structured_weight() -> None:
    # §4.1.1.2 "Structured weight (ex. domain-conditional)"
    from url4.core.nodes import Source

    node = parse("claude:(science:0.85,math:0.64,classics:0.10,_default:0.4):https://x")
    assert isinstance(node, Source)
    assert node.weight == {"science": 0.85, "math": 0.64, "classics": 0.10, "_default": 0.4}
    assert node.value == Url("https://x")


def test_structured_weight_with_quoted_values_all_match() -> None:
    # §4.1.1.4 "Structured weight — key with quoted value (all entries match struct-pair)"
    from url4.core.nodes import Source

    node = parse("claude:(formal:'academic',casual:'conversational',_default:'neutral'):https://x")
    assert isinstance(node, Source)
    assert node.weight == {"formal": "academic", "casual": "conversational", "_default": "neutral"}


def test_scalar_budget() -> None:
    # §4.1.1.2 "Scalar budget"
    from url4.core.nodes import Source

    node = parse("claude:0.6:tokens=4000:https://x")
    assert isinstance(node, Source)
    assert node.budgets == (("tokens", "4000"),)


def test_domain_conditional_structured_budget() -> None:
    # §4.1.1.2 "Structured budget (domain-conditional)"
    from url4.core.nodes import Source

    node = parse("claude:0.6:tokens=(science:6000,math:8000,_default:4000):https://x")
    assert isinstance(node, Source)
    assert node.budgets == (("tokens", {"science": 6000, "math": 8000, "_default": 4000}),)


def test_scoped_structured_budget() -> None:
    # §4.1.1.2 "Structured budget (scoped, see §24.4)"
    from url4.core.nodes import Source

    node = parse("claude:0.6:tokens=(_each:4000,_total:5000000):https://x")
    assert isinstance(node, Source)
    assert node.budgets == (("tokens", {"_each": 4000, "_total": 5000000}),)


def test_nested_scoped_domain_conditional_budget() -> None:
    # §4.1.1.2 "Nested Structured Budgets" — scope → domain → scalar
    from url4.core.nodes import Source

    node = parse("claude:0.6:tokens=(_each:(science:6000,_default:4000),_total:5000000):https://x")
    assert isinstance(node, Source)
    assert node.budgets == (
        ("tokens", {"_each": {"science": 6000, "_default": 4000}, "_total": 5000000}),
    )


# --- §4.1.1.4 first-entry classification: expression source lists -------------


def test_uri_scheme_after_colon_is_expression_list() -> None:
    # §4.1.1.4 valid example — "url4" looks like a key, but "//" follows the colon
    node = parse("claude:(url4://analyst.ai/v1, https://data.com)!'Analyze'")
    assert node == Binding(
        "claude",
        Expression(
            sources=(Url("url4://analyst.ai/v1"), Url("https://data.com")),
            intent=Text("Analyze"),
        ),
        ":",
    )


def test_quoted_first_entry_is_expression_list() -> None:
    # §4.1.1.4 valid example — first token is a quoted string, not an identifier
    node = parse("claude:('some text', https://data.com)!'Summarize'")
    assert node == Binding(
        "claude",
        Expression(sources=(Text("some text"), Url("https://data.com")), intent=Text("Summarize")),
        ":",
    )


def test_relative_uri_first_entry_is_expression_list() -> None:
    # §4.1.1.4 valid example — first token is a relative URI
    from url4.core.nodes import RelUrl

    node = parse("claude:(/api/data, /api/more)!'Merge'")
    assert node == Binding(
        "claude",
        Expression(sources=(RelUrl("/api/data"), RelUrl("/api/more")), intent=Text("Merge")),
        ":",
    )


def test_identifier_colon_slash_is_expression_list() -> None:
    # §4.1.1.4 rule 5a — ':' immediately followed by '/' → URI-ish, expression list
    node = parse("claude:(x:/api/d, /api/m)!'go'")
    assert isinstance(node, Binding)
    assert isinstance(node.value, Expression)


def test_mixed_entries_rule_5d_is_expression_list() -> None:
    # §4.1.1.4 rule 5d — first entry looks like a struct-pair, second is a URI
    node = parse("claude:(label:'test', https://data.com)!'Process'")
    assert isinstance(node, Binding)
    assert isinstance(node.value, Expression)
    assert node.value.sources[1] == Url("https://data.com")
    first = node.value.sources[0]
    assert isinstance(first, Binding) and first.name == "label"


# --- §4.1.1.4 no-backtrack commitment: malformed structured annotations -------


def test_commitment_then_uri_entry_is_malformed() -> None:
    # §4.1.1.4 error example — first entry commits to struct, second is a URI
    with pytest.raises(ParseError) as exc_info:
        parse("claude:(_default:0.4, url4://data.com):https://x")
    assert exc_info.value.code == "malformed_source"


def test_commitment_then_uri_valued_pair_is_malformed() -> None:
    # §4.1.1.4 error example — third entry has a URI-shaped value
    with pytest.raises(ParseError) as exc_info:
        parse("claude:(science:0.85, math:0.64, ref:https://data.com):https://x")
    assert exc_info.value.code == "malformed_source"


def test_parse_error_carries_malformed_source_code() -> None:
    # Contract #9 — ParseError defaults to code "malformed_source"
    with pytest.raises(ParseError) as exc_info:
        parse("(unclosed")
    assert exc_info.value.code == "malformed_source"
