"""Spec §3.3 / §7 — HTTP wire concerns: depth-aware expression-bearing
parameter extraction and sub-request encoding."""

from __future__ import annotations

from url4.core.subrequest import decode_subrequest, encode_subrequest

# --- §3.3.1 expression-bearing parameter extraction --------------------------------


def test_ampersand_inside_parens_stays_in_q() -> None:
    # §3.3.1 — & at depth > 0 is part of the expression, not a param separator
    from url4.core.subrequest import extract_expression_params

    params, q = extract_expression_params(
        "delivery=sync&q=(https://api.com/s?q=hello&limit=100)!'Summarize'"
    )
    assert params == {"delivery": "sync"}
    assert q == "(https://api.com/s?q=hello&limit=100)!'Summarize'"


def test_nested_canonical_expression_keeps_inner_ampersand() -> None:
    # §3.3.1 second example — nested /claude?t=90&q=... inside q=
    from url4.core.subrequest import extract_expression_params

    params, q = extract_expression_params("q=(/claude?t=90&q=($data)!'Answer')!'Use $1'")
    assert params == {}
    assert q == "(/claude?t=90&q=($data)!'Answer')!'Use $1'"


def test_depth_zero_ampersand_terminates_q() -> None:
    # §3.3.1 parsing rule 3 — & at depth 0 outside quotes terminates the value
    from url4.core.subrequest import extract_expression_params

    params, q = extract_expression_params("q=(x)!go&meta=full")
    assert q == "(x)!go"
    assert params == {"meta": "full"}


def test_multiple_protocol_params_before_q() -> None:
    # §3.1 canonical form — protocol params precede q=
    from url4.core.subrequest import extract_expression_params

    params, q = extract_expression_params("delivery=stream&quorum=2&meta=full&q=(a)!'go'")
    assert params == {"delivery": "stream", "quorum": "2", "meta": "full"}
    assert q == "(a)!'go'"


def test_query_without_q_returns_none() -> None:
    # §3.3.1 — a query string with no expression-bearing parameter
    from url4.core.subrequest import extract_expression_params

    params, q = extract_expression_params("limit=10&offset=3")
    assert params == {"limit": "10", "offset": "3"}
    assert q is None


# --- §5.4 / §7.3 sub-request encoding -------------------------------------------------


def test_encode_with_protocol_params() -> None:
    # §5.4 canonical form — params appear as ?&-separated parameters before q=
    from url4.core.subrequest import encode_subrequest as enc

    assert enc("/claude", "ctx", "go", params=(("t", "90"),)) == "/claude?t=90&q=(ctx)!go"


def test_encode_escapes_spaces() -> None:
    # §7.3 — space MUST be encoded on the HTTP wire (contract #16)
    assert encode_subrequest("/p", "a b", "c d") == "/p?q=(a%20b)!c%20d"


def test_decode_round_trips_spaces() -> None:
    # §7.4 — percent-decoding restores the expression text
    assert decode_subrequest("(a%20b)!c%20d") == ("a b", "c d")


def test_encode_decode_round_trip_structural_chars() -> None:
    # §7.4 pipeline — parens/& in content survive the wire
    encoded = encode_subrequest("/reduce", "", 'rows: ["a (1)", "b & c"]')
    _, _, query = encoded.partition("?q=")
    context, intent = decode_subrequest(query)
    assert context == ""
    assert intent == 'rows: ["a (1)", "b & c"]'


def test_extract_then_decode_pipeline() -> None:
    # §7.4 — server pipeline: extract q=, then decode the payload
    from url4.core.subrequest import extract_expression_params

    params, q = extract_expression_params("t=90&q=(a%20b)!go")
    assert params == {"t": "90"}
    assert q is not None
    assert decode_subrequest(q) == ("a b", "go")
