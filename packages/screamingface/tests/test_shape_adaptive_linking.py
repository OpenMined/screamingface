"""The public Benchmark seam binds exactly one complete Candidate Recipe."""

from __future__ import annotations

import pytest
from url4 import build, render

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.linking import link_candidate


def _candidate_url4() -> str:
    return compile_candidate(
        sf.Fusion(
            ["provider/a", "provider/b"],
            synthesizer="provider/synth",
        )
    ).url4


def test_whole_candidate_text_binding_links_one_complete_recipe() -> None:
    benchmark = "(answer:0.0:/candidate(question)!'$candidate')!'$answer'"

    linked = link_candidate(_candidate_url4(), benchmark)

    assert render(build(linked.url4)) == linked.url4
    assert linked.url4.count("candidate:0.0:") == 1
    assert "/provider/a" in linked.url4
    assert "/provider/b" in linked.url4
    assert "/provider/synth" in linked.url4
    assert "/candidate" in linked.url4


def test_whole_candidate_source_binding_is_detected() -> None:
    benchmark = "(answer:0.0:($candidate)!'go')!'$answer'"

    linked = link_candidate(_candidate_url4(), benchmark)

    assert render(build(linked.url4)) == linked.url4
    assert "$candidate" in linked.url4


@pytest.mark.parametrize(
    "reference",
    [
        "$candidate_member_1",
        "$candidate_members",
        "$candidate_synthesizer",
    ],
)
def test_structural_candidate_bindings_are_rejected(reference: str) -> None:
    benchmark = f"(answer:0.0:/candidate(question)!'{reference}')!'$answer'"

    with pytest.raises(sf.PlanningError, match="unsupported structural Candidate") as caught:
        link_candidate(_candidate_url4(), benchmark)

    assert caught.value.code == "candidate_shape_mismatch"


def test_mixed_whole_and_structural_bindings_are_rejected() -> None:
    benchmark = (
        "(answer:0.0:/candidate(question)!'$candidate', "
        "member:0.0:/candidate(question)!'$candidate_member_1')!'$answer'"
    )

    with pytest.raises(sf.PlanningError, match="unsupported structural Candidate") as caught:
        link_candidate(_candidate_url4(), benchmark)

    assert caught.value.code == "candidate_shape_mismatch"


def test_benchmark_without_candidate_binding_is_rejected() -> None:
    benchmark = "(answer:0.0:/fixed(question)!'answer')!'$answer'"

    with pytest.raises(sf.PlanningError, match="does not invoke the Candidate") as caught:
        link_candidate(_candidate_url4(), benchmark)

    assert caught.value.code == "invalid_benchmark_resource"


def test_similarly_named_plumbing_is_not_a_candidate_binding() -> None:
    benchmark = "(answer:0.0:/fixed(question)!'$candidate_result')!'$answer'"

    with pytest.raises(sf.PlanningError, match="does not invoke the Candidate") as caught:
        link_candidate(_candidate_url4(), benchmark)

    assert caught.value.code == "invalid_benchmark_resource"
