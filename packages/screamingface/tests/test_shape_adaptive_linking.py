"""Universal synthesizer and dynamic direct-member bindings.

FEATURE: Benchmark Variants whose URL4 binds a Fusion's direct members and synthesizer.
STORY: as a researcher, I hand any exam my Fusion and the SDK satisfies whatever the
exam's URL4 names — members, synthesizer, or the whole Candidate — without ever
interpreting the protocol.
"""

from __future__ import annotations

import base64
import json
import re

import pytest

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.linking import link_candidate
from screamingface.errors import PlanningError

_JUDGE_SHAPED_BENCHMARK = (
    "(answer_1:0.0:/candidate?q=($item.input)!'$candidate_model_member_1', "
    "answer_2:0.0:/candidate?q=($item.input)!'$candidate_model_member_2', "
    "pick:0.0:/candidate?q=(verdicts)!'$candidate_synthesizer')!'$pick'"
)
_WHOLE_CANDIDATE_BENCHMARK = "(answer:0.0:/candidate?q=($item.input)!'$candidate')!'$answer'"
_MEMBER_COLLECTION_BENCHMARK = (
    "(validated:0.0:/bench/validate('$candidate_members')!'validate', "
    "answers:0.0:$validated*(answer:0.0:/candidate?q=(question)!'$item.expression')!"
    "'$answer', pick:0.0:/candidate?q=($answers)!'$candidate_synthesizer')!'$pick'"
)


def _compiled(recipe):
    return compile_candidate(recipe, default_synthesizer="provider/default")


def test_a_fusion_links_its_synthesizer_into_a_judge_shaped_benchmark() -> None:
    fusion = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        name="pair",
        synthesizer="provider/judge",
    )
    value = _compiled(fusion)
    assert value.synthesizer_expression is not None
    assert "provider/judge" in value.synthesizer_expression

    linked = link_candidate(
        value.url4,
        _JUDGE_SHAPED_BENCHMARK,
        value.member_expressions,
        value.synthesizer_expression,
    )
    assert "candidate_synthesizer" in linked.url4
    assert linked.member_indices == (1, 2)


def test_a_fusion_without_an_explicit_synthesizer_binds_the_default() -> None:
    fusion = sf.Fusion([sf.Model("provider/a"), sf.Model("provider/b")], name="pair")
    value = _compiled(fusion)
    assert value.synthesizer_expression is not None
    assert "provider/default" in value.synthesizer_expression


def test_a_solo_model_against_a_judge_shaped_benchmark_fails_loudly() -> None:
    # INVARIANT: shape mismatches are planning-time errors that name the fix — the
    # protocol needs a judge, so the Candidate must be a Fusion.
    value = _compiled(sf.Model("provider/solo"))
    assert value.synthesizer_expression is None
    with pytest.raises(PlanningError) as caught:
        link_candidate(
            value.url4,
            _JUDGE_SHAPED_BENCHMARK,
            value.member_expressions,
            value.synthesizer_expression,
        )
    assert caught.value.code == "candidate_shape_mismatch"
    assert "synthesizer" in str(caught.value)
    assert "sf.Fusion" in str(caught.value)


def test_a_model_has_no_synthesizer_expression_and_whole_binding_still_works() -> None:
    value = _compiled(sf.Model("provider/solo"))
    linked = link_candidate(
        value.url4,
        _WHOLE_CANDIDATE_BENCHMARK,
        value.member_expressions,
        value.synthesizer_expression,
    )
    assert linked.uses_whole_candidate
    assert "candidate_synthesizer" not in linked.url4


@pytest.mark.parametrize("member_count", [2, 3, 4])
def test_one_member_collection_binding_handles_every_supported_fusion_size(
    member_count: int,
) -> None:
    fusion = sf.Fusion(
        [sf.Model(f"provider/member-{index}") for index in range(1, member_count + 1)],
        name="panel",
        synthesizer="provider/judge",
    )
    value = _compiled(fusion)

    linked = link_candidate(
        value.url4,
        _MEMBER_COLLECTION_BENCHMARK,
        value.member_expressions,
        value.synthesizer_expression,
    )

    assert linked.member_indices == tuple(range(1, member_count + 1))
    assert "$candidate_members" in linked.url4
    assert "$candidate_synthesizer" in linked.url4
    assert "$candidate_model_member_" not in linked.url4
    match = re.search(r"candidate_members:0\.0:'([^']+)'", linked.url4)
    assert match is not None
    payload = json.loads(base64.urlsafe_b64decode(match.group(1)))
    for index in range(1, member_count + 1):
        assert f"provider/member-{index}" in payload[index - 1]["expression"]
        assert payload[index - 1]["key"] == chr(64 + index)
    assert json.loads(json.dumps(linked.url4)) == linked.url4
