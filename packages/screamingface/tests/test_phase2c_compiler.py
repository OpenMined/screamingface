from __future__ import annotations

import pytest
from url4 import build

import screamingface as sf
from screamingface._compiler import compile_fusion


def test_majority_recipe_is_canonical_parameterized_and_network_free() -> None:
    sf.config(engine="http://engine-that-does-not-exist.invalid")
    fusion = sf.Fusion(
        "frontier",
        [
            "codex/gpt-5.5",
            {
                "model": "gemini/2.5",
                "params": {"temperature": 0.2, "enabled": True},
            },
        ],
        reducer=sf.reducers.MajorityVote(),
    )

    recipe = fusion.url4

    assert build(recipe)
    assert "question=" not in recipe
    assert "panel_1=/codex/gpt-5.5($question)!'Answer the question.'" in recipe
    assert "/gemini/2.5?temperature=0.2&enabled=true&q=($question)" in recipe
    assert "fusion_answer=/reducers/majority-vote($panel_answers)" in recipe
    assert "schema: 'screamingface.fusion-result.v1'" in recipe
    assert fusion.prompt == "Answer the question."


def test_concrete_expression_binds_literal_question_without_a_reference() -> None:
    fusion = sf.Fusion(
        "money",
        ["codex/gpt-5.5", "gemini/2.5"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_fusion(fusion, question="What does $5 buy?")

    assert build(expression)
    assert "question='What does $$5 buy?'" in expression
    assert "sealed answer" not in expression


def test_model_reducer_receives_automatic_labeled_context_and_its_own_intent() -> None:
    fusion = sf.Fusion(
        "synthesis",
        ["codex/gpt-5.5", "gemini/2.5"],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Synthesize the panel answers.",
            params={"temperature": 0.0},
        ),
    )

    recipe = fusion.url4

    assert "fusion_answer=/codex/gpt-5.5?temperature=0.0&q=(Question:" in recipe
    assert "$question\n\nPanel answers:\nPanel 1 [codex/gpt-5.5]:\n$panel_1" in recipe
    assert "Panel 2 [gemini/2.5]:\n$panel_2" in recipe
    assert ")!'Synthesize the panel answers.'" in recipe


def test_unknown_reducer_has_no_fallback_compilation() -> None:
    class Other(sf.Reducer):
        kind = "other"

    fusion = sf.Fusion("other", ["a", "b"], reducer=Other())

    with pytest.raises(sf.UnsupportedReducerError, match="unsupported reducer"):
        _ = fusion.url4
