from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

import screamingface as sf
from screamingface.model_inputs import ParameterValue


def _fusion(name: str, *models: sf.Model | str) -> sf.Fusion:
    return sf.Fusion(name, list(models), reducer=sf.reducers.MajorityVote())


def test_model_is_an_immutable_named_model_call() -> None:
    params = {"temperature": 0.7, "max_tokens": 8192}

    model = sf.Model(
        " Opus Sample 1 ",
        "anthropic/claude-opus-4.8",
        prompt="Answer the research question.",
        params=params,
    )
    params["temperature"] = 0.0

    assert model.name == "opus-sample-1"
    assert model.model == "anthropic/claude-opus-4.8"
    assert model.prompt == "Answer the research question."
    assert model.params == {"temperature": 0.7, "max_tokens": 8192}
    model.params["temperature"] = 0.1
    assert model.params["temperature"] == 0.7
    with pytest.raises(AttributeError):
        model.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.Model("", "provider/model"), "name"),
        (lambda: sf.Model("sample", ""), "model"),
        (lambda: sf.Model("sample", "provider/model", prompt=""), "prompt"),
        (
            lambda: sf.Model(
                "sample",
                "provider/model",
                params=cast(Mapping[str, ParameterValue], []),
            ),
            "mapping",
        ),
        (
            lambda: sf.Model("sample", "provider/model", params={"tools": "web_search"}),
            "reserved",
        ),
    ],
)
def test_model_reuses_existing_model_call_validation(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_fusion_accepts_model_values_without_changing_quickstart_shorthand() -> None:
    opus = sf.Model(
        "opus",
        "anthropic/claude-opus-4.8",
        prompt="Research carefully.",
        params={"temperature": 0.7},
    )
    fusion = sf.Fusion(
        "mixed-inputs",
        models=[
            opus,
            "openai/gpt-5.5",
            {"model": "google/gemini-3.1-pro-preview", "params": {"temperature": 0.2}},
        ],
        reducer=sf.reducers.MajorityVote(),
    )

    assert fusion.models[0] is opus
    assert fusion.models[1] == "openai/gpt-5.5"
    assert isinstance(fusion.models[2], Mapping)
    assert fusion.model_ids == (
        "anthropic/claude-opus-4.8",
        "openai/gpt-5.5",
        "google/gemini-3.1-pro-preview",
    )
    assert "member_1=/anthropic/claude-opus-4.8?temperature=0.7" in fusion.url4
    assert "member_2=/openai/gpt-5.5" in fusion.url4


def test_fusion_monster_is_a_network_free_ordered_system_graph() -> None:
    sf.config(engine="http://engine-that-does-not-exist.invalid")
    opus = sf.Model("opus", "anthropic/claude-opus-4.8")
    gpt = sf.Model("gpt", "openai/gpt-5.5")
    frontier = _fusion("frontier-trio", opus, gpt, "google/gemini-3.1-pro-preview")

    monster = sf.FusionMonster(
        " DRACO Substituted ",
        systems=[opus, gpt, frontier],
    )

    assert monster.name == "draco-substituted"
    assert monster.systems == (opus, gpt, frontier)
    assert frontier.models[:2] == (opus, gpt)
    with pytest.raises(AttributeError):
        monster.name = "changed"  # type: ignore[misc]


def test_fusion_monster_allows_one_shared_and_one_fusion_only_model() -> None:
    shared = sf.Model("shared", "provider/shared")
    fusion_only = sf.Model("fusion-only", "provider/only")
    left = _fusion("left", shared, fusion_only)
    right = _fusion("right", shared, "provider/inline")

    monster = sf.FusionMonster("reuse", systems=[shared, left, right])

    assert monster.systems == (shared, left, right)
    assert left.models == (shared, fusion_only)
    assert right.models[0] is shared


def test_fusion_monster_validates_its_system_collection() -> None:
    with pytest.raises(TypeError, match="sequence"):
        sf.FusionMonster("invalid", systems=cast(Sequence[sf.Model | sf.Fusion], "not-a-sequence"))
    with pytest.raises(ValueError, match="at least two"):
        sf.FusionMonster("invalid", systems=[sf.Model("only", "provider/model")])
    with pytest.raises(TypeError, match="sf.Model or sf.Fusion"):
        sf.FusionMonster(
            "invalid",
            systems=cast(
                Sequence[sf.Model | sf.Fusion],
                [sf.Model("one", "provider/one"), "provider/two"],
            ),
        )


def test_fusion_monster_rejects_duplicate_top_level_system_names() -> None:
    first = sf.Model("same", "provider/one")
    second = sf.Model("same", "provider/two")

    with pytest.raises(ValueError, match="system names must be unique.*same"):
        sf.FusionMonster("duplicates", systems=[first, second])


def test_fusion_monster_rejects_distinct_model_objects_with_one_dependency_name() -> None:
    first = sf.Model("sample", "provider/model", params={"temperature": 0.1})
    second = sf.Model("sample", "provider/model", params={"temperature": 0.9})
    left = _fusion("left", first, "provider/other")
    right = _fusion("right", second, "provider/another")

    with pytest.raises(ValueError, match="model dependency name.*sample.*ambiguous"):
        sf.FusionMonster("ambiguous", systems=[left, right])


def test_two_samples_of_the_same_route_require_distinct_names() -> None:
    first = sf.Model("opus-sample-1", "anthropic/claude-opus-4.8")
    second = sf.Model("opus-sample-2", "anthropic/claude-opus-4.8")
    combined = _fusion("combined", first, second)

    monster = sf.FusionMonster(
        "self-fusion",
        systems=[first, second, combined],
    )

    assert monster.systems == (first, second, combined)
    assert combined.models == (first, second)


def test_fusion_monster_rejects_a_system_dependency_name_collision() -> None:
    dependency = sf.Model("synthesis", "provider/model")
    synthesis = _fusion("synthesis", dependency, "provider/other")
    comparison = _fusion("comparison", "provider/a", "provider/b")

    with pytest.raises(ValueError, match="name.*synthesis.*both a system and model dependency"):
        sf.FusionMonster("collision", systems=[synthesis, comparison])


def test_no_discarded_generic_or_solo_aliases_are_exported() -> None:
    assert not hasattr(sf, "Experiment")
    assert not hasattr(sf, "Solo")
    assert not hasattr(sf, "Lineup")
