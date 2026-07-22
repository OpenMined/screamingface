from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

import pytest
from url4 import Url4Node, evaluate_sync

import screamingface as sf
from screamingface._compiler import compile_recipe


def test_model_is_the_small_atomic_recipe() -> None:
    params = {"temperature": 0.7}
    model = sf.Model(
        "anthropic/claude-opus-4.8",
        name=" Opus Sample 1 ",
        prompt="Answer carefully.",
        params=params,
    )
    params["temperature"] = 0.0

    assert isinstance(model, sf.Recipe)
    assert model.name == "opus-sample-1"
    assert model.model == "anthropic/claude-opus-4.8"
    assert model.prompt == "Answer carefully."
    assert model.params == {"temperature": 0.7}
    assert model.members == ()
    assert model.reducer is None
    assert model.params is not model.params


def test_recipe_is_a_public_non_constructible_interface() -> None:
    with pytest.raises(TypeError, match="abstract"):
        cast(Any, sf.Recipe)()


def test_minimal_model_defaults_to_route_leaf_and_default_prompt() -> None:
    model = sf.Model("codex/gpt-5.5")

    assert model.name == "gpt-5.5"
    assert model.prompt == "Answer the question."


def test_explicit_model_name_overrides_route_leaf() -> None:
    model = sf.Model("openrouter/anthropic/claude-opus-4.8", name="Opus Sample 1")

    assert model.name == "opus-sample-1"


def test_fusion_is_composite_and_normalizes_string_shorthand() -> None:
    opus = sf.Model("anthropic/claude-opus-4.8", name="opus")
    fusion = sf.Fusion(
        "frontier",
        members=[opus, "openai/gpt-5.5"],
        reducer=sf.reducers.MajorityVote(),
    )

    assert isinstance(fusion, sf.Recipe)
    assert fusion.name == "frontier"
    assert fusion.members[0] is opus
    assert isinstance(fusion.members[1], sf.Model)
    assert fusion.members[1].model == "openai/gpt-5.5"
    assert fusion.members[1].name == "gpt-5.5"
    assert fusion.model_ids == ("anthropic/claude-opus-4.8", "openai/gpt-5.5")


def test_nested_fusions_and_shared_recipe_identity_compile_once() -> None:
    shared = sf.Model("provider/shared", name="shared")
    left = sf.Fusion(
        "left",
        members=[shared, "provider/left"],
        reducer=sf.reducers.Model(model="provider/judge", prompt="Reduce left."),
    )
    root = sf.Fusion(
        "root",
        members=[left, shared],
        reducer=sf.reducers.Model(model="provider/judge", prompt="Reduce root."),
    )

    recipe = root.url4

    assert recipe.count("/provider/shared") == 1
    assert recipe.count("/provider/left") == 1
    assert "schema: 'screamingface.recipe-result.v1'" in recipe


def test_model_and_fusion_execute_through_the_same_recipe_compiler() -> None:
    model = sf.Model("provider/solo", prompt="Answer directly.")
    node = Url4Node("recipe")

    @node.endpoint("/provider/solo")
    def solo(_request):
        return "answer"

    result = evaluate_sync(compile_recipe(model, question="Question"), node)
    payload = json.loads(result.text)

    assert payload == {
        "schema": "screamingface.recipe-result.v1",
        "members": {
            "member_1": {"model": "provider/solo", "answer": "answer"},
        },
        "answer": "answer",
    }


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: sf.Fusion(
                "empty",
                members=[],
                reducer=sf.reducers.MajorityVote(),
            ),
            "at least one member",
        ),
        (
            lambda: sf.Fusion(
                "mapping",
                members=cast(
                    Sequence[str | sf.Model | sf.Fusion],
                    [{"model": "provider/model"}],
                ),
                reducer=sf.reducers.MajorityVote(),
            ),
            "model IDs, sf.Model, or sf.Fusion",
        ),
        (
            lambda: cast(Any, sf.Fusion)(
                "old-inputs",
                inputs=["provider/one", "provider/two"],
                reducer=sf.reducers.MajorityVote(),
            ),
            "unexpected keyword argument 'inputs'",
        ),
        (
            lambda: cast(Any, sf.Fusion)("atomic", model="provider/model"),
            "unexpected keyword argument 'model'",
        ),
    ],
)
def test_discarded_recursive_fusion_shapes_do_not_survive(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_no_top_level_execution_or_graph_container_aliases() -> None:
    assert not callable(getattr(sf, "run", None))
    assert not callable(getattr(sf, "evaluate", None))
    assert not callable(getattr(sf, "compare", None))
    assert not hasattr(sf, "FusionMonster")
