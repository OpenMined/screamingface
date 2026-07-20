from __future__ import annotations

import pytest
from url4 import Url4Node, build, evaluate_sync

import screamingface as sf
from screamingface._compiler import compile_fusion


def test_majority_recipe_is_canonical_parameterized_and_network_free() -> None:
    sf.config(engine="http://engine-that-does-not-exist.invalid")
    fusion = sf.Fusion(
        "frontier",
        [
            "codex/gpt-5.5",
            {
                "model": "gemini/2.5-flash",
                "params": {"temperature": 0.2, "enabled": True},
            },
        ],
        reducer=sf.reducers.MajorityVote(),
    )

    recipe = fusion.url4

    assert build(recipe)
    assert "question=" not in recipe
    assert "member_1=/codex/gpt-5.5($question)!'Answer the question.'" in recipe
    assert "/gemini/2.5-flash?temperature=0.2&enabled=true&q=($question)" in recipe
    assert "fusion_answer=/reducers/majority-vote($member_answers)" in recipe
    assert "schema: 'screamingface.fusion-result.v1'" in recipe
    assert fusion.prompt == "Answer the question."


def test_concrete_expression_binds_literal_question_without_a_reference() -> None:
    fusion = sf.Fusion(
        "money",
        ["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_fusion(fusion, question="What does $5 buy?")

    assert build(expression)
    assert "question='What does $$5 buy?'" in expression
    assert "sealed answer" not in expression


def test_benchmark_tools_compile_only_onto_members_and_round_trip_through_url4() -> None:
    fusion = sf.Fusion(
        "research",
        ["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_fusion(
        fusion,
        question="Research this",
        tools=("web_search", "code_execution"),
    )

    assert build(expression)
    assert expression.count("?tools=web_search+code_execution&q=($question)") == 2
    assert "fusion_answer=/reducers/majority-vote($member_answers)" in expression
    assert "fusion_answer=/reducers/majority-vote?" not in expression
    assert "tools=" not in fusion.url4

    requests = []
    reducer_requests = []
    node = Url4Node("tool-round-trip")

    def member(request):
        requests.append(request)
        return "A"

    node.endpoint("/codex/gpt-5.5")(member)
    node.endpoint("/gemini/2.5-flash")(member)

    def reduce(request):
        reducer_requests.append(request)
        return "A"

    node.endpoint("/reducers/majority-vote")(reduce)

    result = evaluate_sync(expression, node)

    assert result.text
    assert len(requests) == 2
    assert all(request.params == {"tools": "web_search code_execution"} for request in requests)
    assert len(reducer_requests) == 1
    assert reducer_requests[0].params == {}


def test_model_reducer_receives_automatic_labeled_context_and_its_own_intent() -> None:
    fusion = sf.Fusion(
        "synthesis",
        ["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Synthesize the panel answers.",
            params={"temperature": 0.0},
        ),
    )

    recipe = compile_fusion(fusion, tools=("web_search",))

    assert recipe.count("?tools=web_search&q=($question)") == 2
    assert "fusion_answer=/codex/gpt-5.5?temperature=0.0&q=(Question:" in recipe
    assert "fusion_answer=/codex/gpt-5.5?tools=" not in recipe
    assert "$question\n\nPanel answers:\nPanel 1 [codex/gpt-5.5]:\n$member_1" in recipe
    assert "Panel 2 [gemini/2.5-flash]:\n$member_2" in recipe
    assert ")!'Synthesize the panel answers.'" in recipe


def test_unknown_reducer_has_no_fallback_compilation() -> None:
    class Other(sf.Reducer):
        kind = "other"

    fusion = sf.Fusion("other", ["a", "b"], reducer=Other())

    with pytest.raises(sf.UnsupportedReducerError, match="unsupported reducer"):
        _ = fusion.url4
