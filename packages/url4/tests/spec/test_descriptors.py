"""Spec §4.3 / §4.5 — the full two-axis source descriptor syntax.

Every complete-descriptor example from the spec parses to the frozen-contract
AST: name-only forms stay ``Binding``; anything carrying weight, budgets, exec
annotations, or the expansion mark wraps in ``Source``.
"""

from __future__ import annotations

from url4.grammar import parse
from url4.nodes import Binding, Expression, RelExpr, Text, Url


def test_bare_source_no_annotations() -> None:
    # §4.5 "Bare source (no annotations)"
    assert parse("https://news.com/story") == Url("https://news.com/story")


def test_named_only_sugar_form_is_binding() -> None:
    # §4.5 "Named only (sugar form)" — name-only → Binding (contract #2)
    assert parse("article=https://news.com/story") == Binding(
        "article", Url("https://news.com/story"), "="
    )


def test_named_only_general_form_is_binding() -> None:
    # §4.3 "the sugar form name=value is equivalent to name:value"
    node = parse("article:https://news.com/story")
    assert node == Binding("article", Url("https://news.com/story"), ":")


def test_named_and_weighted() -> None:
    # §4.5 "Named and weighted"
    from url4.nodes import Source

    assert parse("article:0.9:https://news.com/story") == Source(
        value=Url("https://news.com/story"), name="article", weight=0.9
    )


def test_unnamed_weighted() -> None:
    # §4.5 "Unnamed, weighted" — s3:// is an absolute URI (any scheme)
    from url4.nodes import Source

    assert parse("0.8:s3://bucket/train.parquet") == Source(
        value=Url("s3://bucket/train.parquet"), weight=0.8
    )


def test_named_weighted_budgeted_with_required() -> None:
    # §4.5 "Named, weighted, budgeted"
    from url4.nodes import Source

    assert parse("article:0.9:tokens=4000:https://news.com/story;required") == Source(
        value=Url("https://news.com/story"),
        name="article",
        weight=0.9,
        budgets=(("tokens", "4000"),),
        annotations=(("required", None),),
    )


def test_explicit_src_binding_equals_implicit() -> None:
    # §4.5 "Named, weighted, budgeted (explicit src=)" — identical AST
    implicit = parse("article:0.9:tokens=4000:https://news.com/story;required")
    explicit = parse("article:0.9:tokens=4000:src=https://news.com/story;required")
    assert implicit == explicit


def test_unnamed_weighted_quoted_with_exec_annotations() -> None:
    # §4.5 "Unnamed, weighted, with execution annotations" — quotes stripped
    from url4.nodes import Source

    assert parse("0.2:'Supplementary AMA guidelines';optional;retry=3") == Source(
        value=Text("Supplementary AMA guidelines"),
        weight=0.2,
        annotations=(("optional", None), ("retry", "3")),
    )


def test_bare_token_value_requires_src() -> None:
    # §4.5 "Unnamed, weighted, bare-token value (src= required)"
    from url4.nodes import Source

    assert parse("0.2:src=mytoken;optional;retry=3") == Source(
        value=Text("mytoken"),
        weight=0.2,
        annotations=(("optional", None), ("retry", "3")),
    )


def test_full_attribution_plus_execution() -> None:
    # §4.5 "Full attribution + execution"
    from url4.nodes import Source

    node = parse(
        "medical:0.5:tokens=8000:influence=0.6:"
        "https://hospital.org/api/patient/42;mode=agent;t=120;retry=2;required"
    )
    assert node == Source(
        value=Url("https://hospital.org/api/patient/42"),
        name="medical",
        weight=0.5,
        budgets=(("tokens", "8000"), ("influence", "0.6")),
        annotations=(("mode", "agent"), ("t", "120"), ("retry", "2"), ("required", None)),
    )


def test_agent_mode_relative_subexpression_sugar() -> None:
    # §4.5 "Agent mode, named, relative sub-expression (sugar form)"
    from url4.nodes import Source

    node = parse("chef:0.4:(/chef(https://allrecipes.com)!'Find recipes');mode=agent;t=120")
    assert node == Source(
        value=Expression(
            sources=(
                RelExpr(
                    path="/chef",
                    context="https://allrecipes.com",
                    intent=Text("Find recipes"),
                ),
            ),
            intent=None,
        ),
        name="chef",
        weight=0.4,
        annotations=(("mode", "agent"), ("t", "120")),
    )


def test_per_source_content_type_preference() -> None:
    # §4.5 "Per-source content type preference" — name + exec chain, no weight
    from url4.nodes import Source

    assert parse("data:https://api.example.com/records;accept=csv;t=30") == Source(
        value=Url("https://api.example.com/records"),
        name="data",
        annotations=(("accept", "csv"), ("t", "30")),
    )


def test_weight_reserved_key_equivalence() -> None:
    # §4.1.1.3 — weight=X in the attribution chain is a weight, not a budget
    assert parse("claude:weight=0.5:https://x") == parse("claude:0.5:https://x")


def test_uri_with_scheme_colon_is_bare_value() -> None:
    # §4.3 disambiguation — "contains :// before any : or ; at depth 0" → bare value
    assert parse("https://a.com/a:b") == Url("https://a.com/a:b")


def test_annotated_uri_no_longer_silently_text() -> None:
    # Gap-report item 1: `name:weight:uri` must NOT collapse into a Text blob.
    node = parse("article:0.9:https://news.com/story")
    assert not isinstance(node, Text)


def test_exec_flag_and_typed_annotation_order_preserved() -> None:
    # §4.2 — the execution chain is ordered; flags carry a None value
    from url4.nodes import Source

    node = parse("a:0.1:https://x;required;t=5")
    assert isinstance(node, Source)
    assert node.annotations == (("required", None), ("t", "5"))
