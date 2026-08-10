"""Universal synthesizer and dynamic direct-member bindings.

FEATURE: Benchmark Variants whose URL4 binds a Fusion's direct members and synthesizer.
STORY: as a researcher, I hand any exam my Fusion and the SDK satisfies whatever the
exam's URL4 names — members, synthesizer, or the whole Candidate — without ever
interpreting the protocol.
"""

from __future__ import annotations

import pytest
from url4 import Expression, Source, StructObject, Text, build, render

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.linking import link_candidate
from screamingface.errors import PlanningError

_JUDGE_SHAPED_BENCHMARK = (
    "(answer_1:0.0:/candidate?q=($item.input)!'$candidate_member_1', "
    "answer_2:0.0:/candidate?q=($item.input)!'$candidate_member_2', "
    "pick:0.0:/candidate?q=(verdicts)!'$candidate_synthesizer')!'$pick'"
)
_WHOLE_CANDIDATE_BENCHMARK = "(answer:0.0:/candidate?q=($item.input)!'$candidate')!'$answer'"
_NO_CANDIDATE_BENCHMARK = "(answer:0.0:/bench/noop($input)!'system')!'$answer'"
_MEMBERS_ONLY_BENCHMARK = "(answer:0.0:/bench/validate($candidate_members)!'system')!'$answer'"
_MEMBER_COLLECTION_BENCHMARK = (
    "(members:0.0:/bench/validate($candidate_members)!'$candidate_synthesizer', "
    "answers:0.0:$members*(answer:0.0:/candidate?q=(question)!'$item.expression')!"
    "'$answer', pick:0.0:/candidate?q=($answers)!'$candidate_synthesizer')!'$pick'"
)


def _compiled(recipe):
    return compile_candidate(recipe)


def test_a_fusion_links_its_synthesizer_into_a_judge_shaped_benchmark() -> None:
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        name="pair",
        synthesizer="provider/judge",
    )
    value = _compiled(fusion)
    assert value.synthesizer is not None
    assert "provider/judge" in value.synthesizer.url4

    linked = link_candidate(
        value.url4,
        _JUDGE_SHAPED_BENCHMARK,
        value.member_expressions,
        value.synthesizer.url4,
    )
    assert "candidate_synthesizer" in linked.url4
    assert linked.uses_synthesizer
    assert linked.member_indices == (1, 2)


def test_structural_synthesizer_keeps_generation_params_but_not_the_blending_prompt() -> None:
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        synthesizer=sf.Model(
            "provider/judge",
            prompt="Blend the member answers into one final answer.",
            params={"max_tokens": 16384, "temperature": 0.2},
        ),
    )

    value = _compiled(fusion)

    assert value.url4 is not None
    assert "Blend the member answers" in value.url4
    assert value.synthesizer is not None
    assert "max_tokens=16384" in value.synthesizer.url4
    assert "temperature=0.2" in value.synthesizer.url4
    # INVARIANT: this binding contributes model policy; the Benchmark owns its Judge
    # instructions, so ordinary whole-Fusion blending prose cannot leak into that protocol.
    assert "Blend the member answers" not in value.synthesizer.url4


def test_a_fusion_without_a_synthesizer_remains_structurally_available() -> None:
    fusion = sf.Fusion([sf.Model("provider/a"), sf.Model("provider/b")], name="pair")
    value = _compiled(fusion)
    assert value.url4 is None
    assert value.synthesizer is None
    assert [member.name for member in value.member_expressions] == ["a", "b"]


def test_a_benchmark_that_never_invokes_the_candidate_is_rejected() -> None:
    value = _compiled(sf.Model("provider/solo"))

    with pytest.raises(PlanningError) as caught:
        link_candidate(value.url4, _NO_CANDIDATE_BENCHMARK)

    assert caught.value.code == "invalid_benchmark_resource"
    assert "does not invoke the Candidate" in str(caught.value)


def test_a_whole_fusion_benchmark_requires_a_complete_fusion() -> None:
    value = _compiled(sf.Fusion([sf.Model("provider/a"), sf.Model("provider/b")]))
    assert value.url4 is None

    with pytest.raises(PlanningError) as caught:
        link_candidate(value.url4, _WHOLE_CANDIDATE_BENCHMARK, value.member_expressions)

    assert caught.value.code == "candidate_shape_mismatch"
    assert "whole Fusion" in str(caught.value)
    assert "synthesizer=" in str(caught.value)


def test_a_member_collection_benchmark_requires_a_fusion() -> None:
    value = _compiled(sf.Model("provider/solo"))

    with pytest.raises(PlanningError) as caught:
        link_candidate(value.url4, _MEMBERS_ONLY_BENCHMARK)

    assert caught.value.code == "candidate_shape_mismatch"
    assert "use an sf.Fusion" in str(caught.value)


def test_a_judge_shaped_benchmark_requires_a_synthesizer() -> None:
    fusion = sf.Fusion([sf.Model("provider/a"), sf.Model("provider/b")], name="pair")
    value = _compiled(fusion)
    assert value.synthesizer is None

    with pytest.raises(PlanningError) as caught:
        link_candidate(
            value.url4,
            _JUDGE_SHAPED_BENCHMARK,
            value.member_expressions,
            None,
        )

    assert caught.value.code == "candidate_shape_mismatch"
    assert "synthesizer=" in str(caught.value)


def test_a_solo_model_against_a_judge_shaped_benchmark_fails_loudly() -> None:
    # INVARIANT: shape mismatches are planning-time errors that name the fix — the
    # protocol needs a judge, so the Candidate must be a Fusion.
    value = _compiled(sf.Model("provider/solo"))
    assert value.synthesizer is None
    with pytest.raises(PlanningError) as caught:
        link_candidate(
            value.url4,
            _JUDGE_SHAPED_BENCHMARK,
            value.member_expressions,
            None,
        )
    assert caught.value.code == "candidate_shape_mismatch"
    assert "synthesizer" in str(caught.value)
    assert "sf.Fusion" in str(caught.value)


def test_plumbing_names_starting_with_candidate_are_not_a_whole_candidate_reference() -> None:
    # INVARIANT: "$candidate_result" (the engine's parameterized-call plumbing binding)
    # must not read as a bare "$candidate" — that false positive bound the full Candidate
    # expression as dead text into every member-shaped run.
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        name="pair",
        synthesizer="provider/judge",
    )
    value = _compiled(fusion)
    benchmark = (
        "(answer_1:0.0:(candidate_result:0.0:/candidate?web_search=false"
        "&q=($item.input)!'$candidate_member_1')!'$candidate_result', "
        "answer_2:0.0:(candidate_result:0.0:/candidate?web_search=false"
        "&q=($item.input)!'$candidate_member_2')!'$candidate_result', "
        "pick:0.0:/candidate?q=(verdicts)!'$candidate_synthesizer')!'$pick'"
    )
    linked = link_candidate(
        value.url4,
        benchmark,
        value.member_expressions,
        value.synthesizer.url4 if value.synthesizer is not None else None,
    )
    assert not linked.uses_whole_candidate
    assert "(candidate:0.0:" not in linked.url4


def test_references_embedded_inside_url4_text_are_linked_structurally() -> None:
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        name="pair",
        synthesizer="provider/judge",
    )
    value = _compiled(fusion)
    assert value.synthesizer is not None
    benchmark = (
        "(answer:0.0:/candidate?q=(question)!"
        "'Compare $candidate_member_1 and $candidate_member_2 using "
        "$candidate_synthesizer')!'$answer'"
    )

    linked = link_candidate(
        value.url4,
        benchmark,
        value.member_expressions,
        value.synthesizer.url4,
    )

    assert linked.member_indices == (1, 2)
    assert linked.uses_synthesizer is True
    assert "provider/a" in linked.url4
    assert "provider/b" in linked.url4
    assert "provider/judge" in linked.url4


def test_a_model_has_no_synthesizer_component_and_whole_binding_still_works() -> None:
    value = _compiled(sf.Model("provider/solo"))
    linked = link_candidate(
        value.url4,
        _WHOLE_CANDIDATE_BENCHMARK,
        value.member_expressions,
        None,
    )
    assert linked.uses_whole_candidate
    assert not linked.uses_synthesizer
    assert "candidate_synthesizer" not in linked.url4


@pytest.mark.parametrize("member_count", [2, 3, 4])
def test_one_native_member_collection_binding_handles_every_supported_fusion_size(
    member_count: int,
) -> None:
    fusion = sf.Fusion(
        [sf.Model(f"provider/member-{index}") for index in range(1, member_count + 1)],
        name="panel",
        synthesizer="provider/judge",
    )
    value = _compiled(fusion)
    assert value.synthesizer is not None

    linked = link_candidate(
        value.url4,
        _MEMBER_COLLECTION_BENCHMARK,
        value.member_expressions,
        value.synthesizer.url4,
    )

    assert linked.member_indices == tuple(range(1, member_count + 1))
    assert "$candidate_members" in linked.url4
    assert "$candidate_synthesizer" in linked.url4
    assert "$candidate_model_member_" not in linked.url4
    assert '"expression"' not in linked.url4
    parsed = build(linked.url4)
    assert isinstance(parsed, Expression)
    collection = next(
        source
        for source in parsed.sources
        if isinstance(source, Source) and source.name == "candidate_members"
    )
    assert isinstance(collection.value, StructObject)
    for index in range(1, member_count + 1):
        binding = next(
            source
            for source in parsed.sources
            if isinstance(source, Source) and source.name == f"candidate_member_{index}"
        )
        assert isinstance(binding.value, Text)
        assert f"provider/member-{index}" in binding.value.value
        assert f"member_{index}: {{name: 'member-{index}', " in collection.value.raw
        assert f"url4: '$candidate_member_{index}'" in collection.value.raw
        # Each executable member appears exactly once; the collection carries only a URL4 ref.
        assert linked.url4.count(f"provider/member-{index}") == 1
    assert render(build(linked.url4)) == linked.url4
