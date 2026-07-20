"""Spec §3.1.1 / §8.1 — sugar ↔ canonical equivalence and the desugaring
boundary algorithm for trailing ``;`` parameters."""

from __future__ import annotations

from url4.core.grammar import parse
from url4.core.nodes import RelUrl, Text


def test_sugar_equals_canonical_relative() -> None:
    # §3.1.1.1 — `/claude($data)!'Answer'` ≡ `/claude?q=($data)!'Answer'`
    assert parse("/claude($data)!'Answer'") == parse("/claude?q=($data)!'Answer'")


def test_sugar_with_param_equals_canonical_relative() -> None:
    # §3.1.1.1 — `/claude($data)!'Answer';t=90` ≡ `/claude?t=90&q=($data)!'Answer'`
    assert parse("/claude($data)!'Answer';t=90") == parse("/claude?t=90&q=($data)!'Answer'")


def test_bare_source_all_trailing_params_are_expression_level() -> None:
    # §8.1.2 — bare source: ALL `;` annotations after intent are expression-level
    from url4.core.nodes import RelExpr

    node = parse("/claude($data)!'Answer';t=90;quorum=2")
    assert node == RelExpr(
        path="/claude",
        context="$data",
        intent=Text("Answer"),
        params=(("t", "90"), ("quorum", "2")),
    )


def test_boundary_algorithm_dual_scope_t() -> None:
    # §8.1.2 — the exact worked example: expression params consumed greedily
    # until the first exclusively-source-level key (mode); t=60 before it is
    # expression-level, t=180 after it is source-level.
    from url4.core.nodes import RelExpr, Source

    node = parse("model:0.5:/claude($data)!'Answer';quorum=2;t=60;mode=agent;t=180;required")
    assert node == Source(
        value=RelExpr(
            path="/claude",
            context="$data",
            intent=Text("Answer"),
            params=(("quorum", "2"), ("t", "60")),
        ),
        name="model",
        weight=0.5,
        annotations=(("mode", "agent"), ("t", "180"), ("required", None)),
    )


def test_annotated_source_simple_exec_chain() -> None:
    # §8.1.4 — common case: no expression-level params, all source-level
    from url4.core.nodes import RelExpr, Source

    node = parse("model:0.5:/claude($item.question)!'Answer';mode=agent")
    assert node == Source(
        value=RelExpr(path="/claude", context="$item.question", intent=Text("Answer")),
        name="model",
        weight=0.5,
        annotations=(("mode", "agent"),),
    )


def test_canonical_makes_dual_scope_explicit() -> None:
    # §8.1.4 — canonical form: ?-params expression-level, ;-chain source-level
    from url4.core.nodes import RelExpr, Source

    node = parse("model:0.5:/claude?t=60&quorum=2&q=($data)!'Answer';mode=agent;t=180;required")
    assert node == Source(
        value=RelExpr(
            path="/claude",
            context="$data",
            intent=Text("Answer"),
            params=(("t", "60"), ("quorum", "2")),
        ),
        name="model",
        weight=0.5,
        annotations=(("mode", "agent"), ("t", "180"), ("required", None)),
    )


def test_relative_data_uri_not_promoted_to_expression() -> None:
    # §5.4 disambiguation — `q=` not followed by '(' → data URI
    assert parse("/api/search?q=hello") == RelUrl("/api/search?q=hello")
    assert parse("/api?limit=10") == RelUrl("/api?limit=10")


def test_remote_sugar_equals_canonical() -> None:
    # §3.1.1.1 — url4://node/v1($d)!'A';quorum=2 ≡ url4://node/v1?quorum=2&q=($d)!'A'
    assert parse("url4://node.ai/v1($d)!'Analyze';quorum=2") == parse(
        "url4://node.ai/v1?quorum=2&q=($d)!'Analyze'"
    )


def test_remote_expression_components() -> None:
    # §3.1 canonical structure — authority, path, params, expression
    from url4.core.nodes import RemoteExpr

    node = parse("url4://node.example.com:8443/v1/ensemble?delivery=sync&q=(x)!'go'")
    assert node == RemoteExpr(
        authority="node.example.com:8443",
        path="/v1/ensemble",
        context="x",
        intent=Text("go"),
        params=(("delivery", "sync"),),
    )
