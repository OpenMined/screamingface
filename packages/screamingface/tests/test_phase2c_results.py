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
    benchmark = _benchmark()
    member = sf.MemberResult("codex/gpt-5.5", " A\n")
    second = sf.MemberResult("gemini/3.5-flash", "B")
    result = sf.CaseResult(
        "q1",
        members={"member_1": member, "member_2": second},
        answer="A",
    )
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="tiny-fusion",
        fusion_url4="(recipe)",
        members={"member_1": member.model, "member_2": second.model},
        cases=benchmark._materialize_cases(),
        results=[result],
    )

    assert isinstance(result.members, Mapping)
    assert result.members["member_1"] == member
    assert result.members["member_1"].answer == " A\n"
    with pytest.raises(TypeError):
        result.members["member_2"] = member  # type: ignore[index]
    assert run.fusion_name == "tiny-fusion"
    assert run.members == {
        "member_1": "codex/gpt-5.5",
        "member_2": "gemini/3.5-flash",
    }
    with pytest.raises(TypeError):
        run.members["member_1"] = "other/model"  # type: ignore[index]
    assert run.case_ids == ("q1",)
    assert run.failures == ()
    assert run.complete is True
    assert json.loads(json.dumps(run.to_dict())) == run.to_dict()
    assert run.to_dict()["fusion_name"] == "tiny-fusion"
    assert run.to_dict()["members"] == {
        "member_1": "codex/gpt-5.5",
        "member_2": "gemini/3.5-flash",
    }
    with pytest.raises(AttributeError):
        run.results = ()  # type: ignore[misc]


def test_failed_result_is_atomic_and_surfaces_a_standalone_failure() -> None:
    benchmark = _benchmark()
    failure = sf.RunFailure(
        "q1",
        "url4",
        "upstream unavailable",
        status=502,
        code="resolution_failed",
    )
    result = sf.CaseResult("q1", members={}, answer=None, failure=failure)
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="tiny-fusion",
        fusion_url4="(recipe)",
        members={"member_1": "codex/gpt-5.5", "member_2": "gemini/3.5-flash"},
        cases=benchmark._materialize_cases(),
        results=[result],
    )

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
                members={"member_1": sf.MemberResult("model", "answer")},
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


@pytest.mark.parametrize(
    ("members", "results", "message"),
    [
        (
            {"member_2": "model/two", "member_3": "model/three"},
            [],
            "contiguous",
        ),
        (
            {"member_1": "model/one", "member_2": "model/two"},
            [
                sf.CaseResult(
                    "q1",
                    members={"member_1": sf.MemberResult("model/one", "answer")},
                    answer="answer",
                )
            ],
            "slots and order",
        ),
        (
            {"member_1": "model/one", "member_2": "model/two"},
            [
                sf.CaseResult(
                    "q1",
                    members={
                        "member_1": sf.MemberResult("model/one", "answer"),
                        "member_2": sf.MemberResult("model/other", "answer"),
                    },
                    answer="answer",
                )
            ],
            "models",
        ),
    ],
)
def test_run_rejects_member_identity_drift(
    members: dict[str, str],
    results: list[sf.CaseResult],
    message: str,
) -> None:
    if not results:
        results = [
            sf.CaseResult(
                "q1",
                members={
                    "member_2": sf.MemberResult("model/two", "answer"),
                    "member_3": sf.MemberResult("model/three", "answer"),
                },
                answer="answer",
            )
        ]
    benchmark = _benchmark()
    with pytest.raises(ValueError, match=message):
        sf.Run(
            benchmark=benchmark,
            fusion_name="tiny-fusion",
            fusion_url4="(recipe)",
            members=members,
            cases=benchmark._materialize_cases(),
            results=results,
        )


def test_run_rejects_results_that_do_not_match_the_selected_cases() -> None:
    benchmark = _benchmark()
    with pytest.raises(ValueError, match="selected cases"):
        sf.Run(
            benchmark=benchmark,
            fusion_name="tiny-fusion",
            fusion_url4="(recipe)",
            members={"member_1": "model/one", "member_2": "model/two"},
            cases=benchmark._materialize_cases(),
            results=[
                sf.CaseResult(
                    "other",
                    members={
                        "member_1": sf.MemberResult("model/one", "answer"),
                        "member_2": sf.MemberResult("model/two", "answer"),
                    },
                    answer="answer",
                )
            ],
        )
