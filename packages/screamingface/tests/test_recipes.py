from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf


def synthesis(**overrides: object) -> sf.reducers.Synthesis:
    values: dict[str, object] = {
        "instructions": "Combine the strongest supported claims.",
        "temperature": 0.2,
        "reasoning": "low",
        "max_output_tokens": 4096,
    }
    values.update(overrides)
    return sf.reducers.Synthesis(
        "openrouter/anthropic/claude-opus-4.8",
        **cast(Any, values),
    )


def test_model_is_an_immutable_network_free_recipe_with_typed_controls() -> None:
    model = sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        instructions="Answer as a careful researcher.",
        temperature=0.2,
        reasoning="low",
        max_output_tokens=8192,
    )

    assert isinstance(model, sf.Recipe)
    assert model.model == "openrouter/anthropic/claude-opus-4.8"
    assert model.name == "claude-opus-4.8"
    assert model.instructions == "Answer as a careful researcher."
    assert model.temperature == 0.2
    assert model.reasoning == "low"
    assert model.max_output_tokens == 8192
    assert not hasattr(model, "url4")

    with pytest.raises(AttributeError):
        cast(Any, model).temperature = 0.8


def test_explicit_recipe_names_are_trimmed_but_not_rewritten() -> None:
    model = sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        name=" Opus Sample 1 ",
    )

    assert model.name == "Opus Sample 1"


def test_synthesis_is_an_immutable_model_backed_reducer() -> None:
    reducer = synthesis()

    assert isinstance(reducer, sf.Reducer)
    assert reducer.model == "openrouter/anthropic/claude-opus-4.8"
    assert reducer.instructions == "Combine the strongest supported claims."
    assert reducer.temperature == 0.2
    assert reducer.reasoning == "low"
    assert reducer.max_output_tokens == 4096

    with pytest.raises(AttributeError):
        cast(Any, reducer).reasoning = "high"


def test_fusion_keeps_the_original_recipes_in_declared_order() -> None:
    opus = sf.Model("openrouter/anthropic/claude-opus-4.8", name="opus")
    gpt = sf.Model("openrouter/openai/gpt-5.5", name="gpt")
    reducer = synthesis()

    fusion = sf.Fusion(
        "frontier-pair",
        members=[opus, gpt],
        reducer=reducer,
    )

    assert isinstance(fusion, sf.Recipe)
    assert fusion.name == "frontier-pair"
    assert fusion.members == (opus, gpt)
    assert fusion.members[0] is opus
    assert fusion.members[1] is gpt
    assert fusion.reducer is reducer
    assert not hasattr(fusion, "url4")


def test_nested_fusions_are_regular_members() -> None:
    opus = sf.Model("provider/opus", name="opus")
    gpt = sf.Model("provider/gpt", name="gpt")
    gemini = sf.Model("provider/gemini", name="gemini")
    pair = sf.Fusion("pair", members=[opus, gpt], reducer=synthesis())
    trio = sf.Fusion("trio", members=[pair, gemini], reducer=synthesis())

    assert trio.members == (pair, gemini)
    nested = cast(sf.Fusion, trio.members[0])
    assert nested.members == (opus, gpt)


def test_equal_looking_models_remain_independent_recipe_objects() -> None:
    first = sf.Model("provider/opus", name="sample-1", temperature=0.7)
    second = sf.Model("provider/opus", name="sample-2", temperature=0.7)

    assert first is not second
    assert first != second

    fusion = sf.Fusion("self-fusion", members=[first, second], reducer=synthesis())
    assert fusion.members == (first, second)


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ([], "at least two members"),
        ([sf.Model("provider/one")], "at least two members"),
        (
            [sf.Model("provider-a/same"), sf.Model("provider-b/same")],
            "duplicate Fusion member name 'same'",
        ),
        ([sf.Model("provider/one"), "provider/two"], "members must be sf.Model or sf.Fusion"),
    ],
)
def test_fusion_rejects_ambiguous_or_non_composite_members(
    members: list[object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        sf.Fusion(
            "invalid",
            members=cast(Any, members),
            reducer=synthesis(),
        )


def test_fusion_rejects_unpublished_recipe_extensions() -> None:
    class CustomRecipe(sf.Recipe):
        name = "custom"

        @property
        def _recipe_marker(self) -> None:
            return None

    with pytest.raises(TypeError, match="sf.Model or sf.Fusion"):
        sf.Fusion(
            "invalid",
            members=[CustomRecipe(), sf.Model("provider/model")],
            reducer=synthesis(),
        )


@pytest.mark.parametrize(
    ("factory", "error", "message"),
    [
        (
            lambda: sf.Model("provider/model", name=" "),
            ValueError,
            "model name",
        ),
        (
            lambda: sf.Model("provider/model", instructions=""),
            ValueError,
            "instructions",
        ),
        (
            lambda: sf.Model("provider/model", temperature=float("nan")),
            ValueError,
            "temperature",
        ),
        (
            lambda: sf.Model("provider/model", reasoning=" "),
            ValueError,
            "reasoning",
        ),
        (
            lambda: sf.Model("provider/model", max_output_tokens=0),
            ValueError,
            "max_output_tokens",
        ),
        (
            lambda: cast(Any, sf.Model)("provider/model", params={"temperature": 0.2}),
            TypeError,
            "unexpected keyword argument 'params'",
        ),
    ],
)
def test_model_rejects_invalid_or_removed_configuration(
    factory: object,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        cast(Any, factory)()


def test_only_the_v1_reducer_surface_is_public() -> None:
    assert hasattr(sf.reducers, "Synthesis")
    assert not hasattr(sf.reducers, "Model")
    assert not hasattr(sf.reducers, "MajorityVote")


def test_recipe_and_reducer_are_non_constructible_umbrella_types() -> None:
    with pytest.raises(TypeError, match="abstract"):
        cast(Any, sf.Recipe)()
    with pytest.raises(TypeError, match="abstract"):
        cast(Any, sf.Reducer)()


def test_recipe_representations_are_compact_and_researcher_facing() -> None:
    opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
    sample = sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        name="sample-1",
        temperature=0.7,
    )
    gpt = sf.Model("openrouter/openai/gpt-5.5")
    reducer = sf.reducers.Synthesis("openrouter/anthropic/claude-opus-4.8")
    fusion = sf.Fusion("pair", members=[opus, gpt], reducer=reducer)

    assert repr(opus) == "Model('openrouter/anthropic/claude-opus-4.8')"
    assert repr(sample) == (
        "Model('openrouter/anthropic/claude-opus-4.8', name='sample-1', temperature=0.7)"
    )
    assert repr(reducer) == "Synthesis('openrouter/anthropic/claude-opus-4.8')"
    assert repr(fusion) == (
        "Fusion('pair', members=['claude-opus-4.8', 'gpt-5.5'], "
        "reducer=Synthesis('openrouter/anthropic/claude-opus-4.8'))"
    )
