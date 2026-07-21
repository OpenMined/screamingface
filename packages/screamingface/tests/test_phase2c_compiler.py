from __future__ import annotations

import pytest
from url4 import Url4Node, build, evaluate_sync

import screamingface as sf
from screamingface._compiler import (
    _tool_params,
    compile_benchmark_expression,
    compile_model_expression,
    compile_recipe,
)


def test_majority_recipe_is_canonical_parameterized_and_network_free() -> None:
    sf.config(engine="http://engine-that-does-not-exist.invalid")
    gemini = sf.Model(
        "gemini/2.5-flash",
        name="gemini",
        params={"temperature": 0.2, "enabled": True},
    )
    fusion = sf.Fusion(
        "frontier",
        members=[
            "codex/gpt-5.5",
            gemini,
        ],
        reducer=sf.reducers.MajorityVote(),
    )

    recipe = fusion.url4

    assert build(recipe)
    assert "question=" not in recipe
    assert "member_1=/codex/gpt-5.5($question)!'Answer the question.'" in recipe
    assert "/gemini/2.5-flash?temperature=0.2&enabled=true&q=($question)" in recipe
    assert "recipe_answer=/reducers/majority-vote/1()!'$member_answers'" in recipe
    assert "schema: 'screamingface.recipe-result.v1'" in recipe
    assert recipe.endswith(")!'$recipe_result'")
    assert gemini.prompt == "Answer the question."


def test_concrete_expression_binds_literal_question_without_a_reference() -> None:
    fusion = sf.Fusion(
        "money",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_recipe(fusion, question="What does $5 buy?")

    assert build(expression)
    assert "question='What does $$5 buy?'" in expression
    assert "sealed answer" not in expression


def test_benchmark_tools_compile_only_onto_members_and_round_trip_through_url4() -> None:
    fusion = sf.Fusion(
        "research",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_recipe(
        fusion,
        question="Research this",
        tools=(sf.tools.WebSearch(), sf.tools.WebFetch()),
        max_tool_calls=8,
    )

    assert build(expression)
    assert expression.count("tools=web_search:web_fetch") == 2
    assert expression.count("tools.max_calls=8") == 2
    assert "recipe_answer=/reducers/majority-vote/1()!'$member_answers'" in expression
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

    node.endpoint("/reducers/majority-vote/1")(reduce)

    result = evaluate_sync(expression, node)

    assert result.text
    assert len(requests) == 2
    assert all(request.params["tools"] == "web_search:web_fetch" for request in requests)
    assert all(request.params["tools.max_calls"] == "8" for request in requests)
    assert len(reducer_requests) == 1
    assert reducer_requests[0].params == {}
    assert reducer_requests[0].context == ""


def test_official_benchmark_compiles_one_shared_versioned_tool_policy() -> None:
    fusion = sf.Fusion(
        "research",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_benchmark_expression(
        benchmark_id="research@1",
        cases_route="/benchmarks/research/1/cases",
        grader_route="/graders/exact-choice/1",
        aggregator_route="/aggregators/mean/1",
        recipe=fusion,
        tools=(sf.tools.WebSearch(), sf.tools.WebFetch()),
        max_tool_calls=12,
        tool_policy_route="/benchmarks/research/1/tool-policy",
        first=1,
    )

    assert build(expression)
    assert expression.count("tool_policy=/benchmarks/research/1/tool-policy") == 1
    assert expression.count("schema: 'screamingface.model-input.v1'") == 1
    assert expression.count("tool_policy: '$tool_policy'") == 1
    assert expression.count("($model_input)!") == 2
    assert "member_1=/codex/gpt-5.5($model_input)" in expression
    assert "member_2=/gemini/2.5-flash($model_input)" in expression
    assert "tools=" not in expression
    assert "tools.max_calls=" not in expression
    assert "web_search." not in expression
    assert "recipe_answer=/reducers/majority-vote/1()!'$member_answers'" in expression


def test_tool_policy_route_requires_tools() -> None:
    with pytest.raises(ValueError, match="requires benchmark tools"):
        compile_recipe(
            sf.Model("codex/gpt-5.5"),
            question="Question",
            tool_policy_route="/benchmarks/research/1/tool-policy",
        )


def test_model_reducer_receives_automatic_labeled_context_and_its_own_intent() -> None:
    fusion = sf.Fusion(
        "synthesis",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Synthesize the panel answers.",
            params={"temperature": 0.0},
        ),
    )

    recipe = compile_recipe(
        fusion,
        tools=(sf.tools.WebSearch(),),
        max_tool_calls=8,
    )

    assert recipe.count("tools=web_search") == 2
    assert recipe.count("tools.max_calls=8") == 2
    assert "recipe_answer=/codex/gpt-5.5?temperature=0.0&q=(Question:" in recipe
    assert "fusion_answer=/codex/gpt-5.5?tools=" not in recipe
    assert "$question\n\nPanel answers:\nPanel 1 [codex/gpt-5.5]:\n$member_1" in recipe
    assert "Panel 2 [gemini/2.5-flash]:\n$member_2" in recipe
    assert ")!'Synthesize the panel answers.'" in recipe


def test_unknown_reducer_has_no_fallback_compilation() -> None:
    class Other(sf.Reducer):
        kind = "other"

    fusion = sf.Fusion("other", members=["a", "b"], reducer=Other())

    with pytest.raises(sf.UnsupportedReducerError, match="unsupported reducer"):
        _ = fusion.url4


def test_tool_round_configuration_is_strict() -> None:
    with pytest.raises(ValueError, match="must be None"):
        _tool_params((), 1)
    with pytest.raises(ValueError, match="is required"):
        _tool_params((sf.tools.WebSearch(),), None)
    with pytest.raises(ValueError, match="is required"):
        _tool_params((sf.tools.WebSearch(),), True)
    with pytest.raises(ValueError, match="positive integer"):
        _tool_params((sf.tools.WebSearch(),), 0)
    with pytest.raises(ValueError, match="1 to 32"):
        _tool_params((sf.tools.WebSearch(),), 33)


def test_model_expression_accepts_default_parameters() -> None:
    expression = compile_model_expression(
        model="codex/gpt-5.5",
        context="Question",
        intent="Answer",
    )

    assert build(expression)
    assert "model_result=/codex/gpt-5.5($model_context)!'Answer'" in expression
