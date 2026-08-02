from __future__ import annotations

from types import MappingProxyType
from typing import Any, cast

import pytest

import screamingface as sf


def test_model_is_an_immutable_network_free_candidate() -> None:
    model = sf.Model("openrouter/anthropic/claude-opus-4.8")

    assert isinstance(model, sf.Recipe)
    assert model.model == "openrouter/anthropic/claude-opus-4.8"
    assert model.name == "claude-opus-4.8"
    assert not hasattr(model, "instructions")
    assert not hasattr(model, "temperature")
    assert not hasattr(model, "reasoning")
    assert not hasattr(model, "max_output_tokens")
    assert not hasattr(model, "url4")

    with pytest.raises(AttributeError):
        cast(Any, model).model = "provider/other"


def test_explicit_model_name_is_a_trimmed_sample_identity() -> None:
    model = sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        name=" Opus Sample 1 ",
    )

    assert model.name == "Opus Sample 1"
    assert model._sample_id == "Opus Sample 1"


def test_model_accepts_optional_candidate_owned_prompt_and_parameters() -> None:
    model = sf.Model(
        "provider/model",
        prompt="Answer using primary evidence.",
        params={"temperature": 0.4, "reasoning": "high"},
    )

    assert model.prompt == "Answer using primary evidence."
    assert model.params == {"temperature": 0.4, "reasoning": "high"}
    assert isinstance(model.params, MappingProxyType)


def test_fusion_keeps_members_in_order_and_infers_a_name() -> None:
    opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
    gpt = sf.Model("openrouter/openai/gpt-5.5")

    fusion = sf.Fusion([opus, gpt])

    assert isinstance(fusion, sf.Recipe)
    assert fusion.name == "claude-opus-4.8+gpt-5.5"
    assert fusion.members == (opus, gpt)
    assert fusion.members[0] is opus
    assert fusion.members[1] is gpt
    assert not hasattr(fusion, "reducer")
    assert not hasattr(fusion, "url4")


def test_fusion_accepts_an_optional_display_name() -> None:
    fusion = sf.Fusion(
        [sf.Model("provider/opus"), sf.Model("provider/gpt")],
        name=" Frontier ",
    )

    assert fusion.name == "Frontier"


def test_fusion_accepts_optional_candidate_owned_synthesis_policy() -> None:
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        synthesizer="provider/synth",
        prompt="Resolve disagreements using evidence.",
        params={"temperature": 0.1},
    )

    assert fusion.synthesizer == "provider/synth"
    assert fusion.prompt == "Resolve disagreements using evidence."
    assert fusion.params == {"temperature": 0.1}


def test_fusion_needs_no_explicit_synthesizer_policy() -> None:
    fusion = sf.Fusion([sf.Model("provider/a"), sf.Model("provider/b")])

    assert fusion.synthesizer is None
    assert fusion.prompt is None
    assert fusion.params == {}


def test_nested_fusions_are_regular_members() -> None:
    opus = sf.Model("provider/opus")
    gpt = sf.Model("provider/gpt")
    gemini = sf.Model("provider/gemini")
    pair = sf.Fusion([opus, gpt], name="pair")
    trio = sf.Fusion([pair, gemini], name="trio")

    assert trio.members == (pair, gemini)
    nested = cast(sf.Fusion, trio.members[0])
    assert nested.members == (opus, gpt)


def test_explicit_names_distinguish_independent_samples() -> None:
    first = sf.Model("provider/opus", name="sample-1")
    second = sf.Model("provider/opus", name="sample-2")

    assert first is not second
    assert first != second

    fusion = sf.Fusion([first, second], name="self-fusion")
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
        sf.Fusion(cast(Any, members))


def test_fusion_rejects_unpublished_recipe_extensions() -> None:
    class CustomRecipe(sf.Recipe):
        name = "custom"

        @property
        def _recipe_marker(self) -> None:
            return None

    with pytest.raises(TypeError, match="sf.Model or sf.Fusion"):
        sf.Fusion([CustomRecipe(), sf.Model("provider/model")])


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.Model("provider/model", name=" "), "model name"),
        (
            lambda: sf.Fusion(
                [sf.Model("provider/a"), sf.Model("provider/b")],
                name=" ",
            ),
            "fusion name",
        ),
    ],
)
def test_candidates_reject_invalid_names(factory: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        cast(Any, factory)()


@pytest.mark.parametrize(
    "keyword", ["instructions", "temperature", "reasoning", "max_output_tokens"]
)
def test_model_rejects_undeclared_generation_keywords(keyword: str) -> None:
    with pytest.raises(TypeError, match=f"unexpected keyword argument '{keyword}'"):
        cast(Any, sf.Model)("provider/model", **{keyword: object()})


def test_recipe_is_a_non_constructible_umbrella_type() -> None:
    with pytest.raises(TypeError, match="abstract"):
        cast(Any, sf.Recipe)()


def test_candidate_representations_are_compact() -> None:
    opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
    sample = sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        name="sample-1",
    )
    gpt = sf.Model("openrouter/openai/gpt-5.5")

    assert repr(opus) == "Model('openrouter/anthropic/claude-opus-4.8')"
    assert repr(sample) == ("Model('openrouter/anthropic/claude-opus-4.8', name='sample-1')")
    assert repr(sf.Fusion([opus, gpt])) == ("Fusion(['claude-opus-4.8', 'gpt-5.5'])")
    assert repr(sf.Fusion([opus, gpt], name="pair")) == (
        "Fusion(['claude-opus-4.8', 'gpt-5.5'], name='pair')"
    )


def test_candidate_representations_include_behavioral_overrides() -> None:
    model = sf.Model(
        "provider/model",
        name="sample",
        prompt="Use evidence.",
        params={"temperature": 0.2},
    )
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        name="pair",
        synthesizer="provider/synth",
        prompt="Resolve conflicts.",
        params={"reasoning": "high"},
    )

    assert repr(model) == (
        "Model('provider/model', name='sample', prompt='Use evidence.', "
        "params={'temperature': 0.2})"
    )
    assert repr(fusion) == (
        "Fusion(['a', 'b'], name='pair', synthesizer='provider/synth', "
        "prompt='Resolve conflicts.', params={'reasoning': 'high'})"
    )
