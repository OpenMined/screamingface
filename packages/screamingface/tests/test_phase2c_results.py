from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest

import screamingface as sf
from screamingface.run import FailureKind


def _benchmark() -> sf.Benchmark:
    return sf.Benchmark(
        "tiny@1",
        cases=[sf.Case("q1", "Question", reference="A")],
        grader=sf.graders.ExactChoice(),
    )


def test_successful_run_is_immutable_typed_and_json_compatible() -> None:
    member = sf.MemberResult("codex/gpt-5.5", " A\n")
    result = sf.CaseResult(
        "q1",
        members={"panel_1": member},
        answer="A",
    )
    run = sf.Run(benchmark=_benchmark(), fusion_url4="(recipe)", results=[result])

    assert isinstance(result.members, Mapping)
    assert result.members["panel_1"] == member
    assert result.members["panel_1"].answer == " A\n"
    with pytest.raises(TypeError):
        result.members["panel_2"] = member  # type: ignore[index]
    assert run.case_ids == ("q1",)
    assert run.failures == ()
    assert run.complete is True
    assert json.loads(json.dumps(run.to_dict())) == run.to_dict()
    with pytest.raises(AttributeError):
        run.results = ()  # type: ignore[misc]


def test_failed_result_is_atomic_and_surfaces_a_standalone_failure() -> None:
    failure = sf.RunFailure(
        "q1",
        "url4",
        "upstream unavailable",
        status=502,
        code="resolution_failed",
    )
    result = sf.CaseResult("q1", members={}, answer=None, failure=failure)
    run = sf.Run(benchmark=_benchmark(), fusion_url4="(recipe)", results=[result])

    assert result.members == {}
    assert result.answer is None
    assert run.failures == (failure,)
    assert run.complete is False
    assert run.to_dict()["failures"] == [
        {
            "case_id": "q1",
            "kind": "url4",
            "message": "upstream unavailable",
            "status": 502,
            "code": "resolution_failed",
        }
    ]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.MemberResult("model", " "), "answer"),
        (
            lambda: sf.RunFailure("q", cast(FailureKind, "wrong"), "message"),
            "kind",
        ),
        (lambda: sf.RunFailure("q", "http", "message", status=99), "status"),
        (
            lambda: sf.CaseResult("q", members={}, answer="partial", failure=None),
            "requires members",
        ),
        (
            lambda: sf.CaseResult(
                "q",
                members={"panel_1": sf.MemberResult("model", "answer")},
                answer=None,
                failure=sf.RunFailure("q", "timeout", "late"),
            ),
            "partial",
        ),
    ],
)
def test_run_values_reject_inconsistent_state(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()
