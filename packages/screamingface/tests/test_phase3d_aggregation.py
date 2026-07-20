from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

import screamingface as sf
from screamingface import _aggregation, _execution

MEMBERS = {
    "member_1": "worker/one",
    "member_2": "worker/two",
}


def _benchmark(*, aggregator: sf.Aggregator | None = None) -> sf.Benchmark:
    return sf.Benchmark(
        "paired@1",
        cases=[
            sf.Case("q1", "Question one", reference="A"),
            sf.Case("q2", "Question two", reference="B"),
            sf.Case("q3", "Question three", reference="C"),
        ],
        grader=sf.graders.ExactChoice(),
        aggregator=aggregator,
    )


def _result(case_id: str) -> sf.CaseResult:
    return sf.CaseResult(
        case_id,
        members={
            "member_1": sf.MemberResult("worker/one", "answer one"),
            "member_2": sf.MemberResult("worker/two", "answer two"),
        },
        answer="fusion answer",
    )


def _run(benchmark: sf.Benchmark | None = None) -> sf.Run:
    selected_benchmark = benchmark or _benchmark()
    return sf.Run(
        benchmark=selected_benchmark,
        fusion_name="paired-fusion",
        fusion_url4="(recipe)",
        members=MEMBERS,
        cases=selected_benchmark._materialize_cases(),
        results=[_result("q1"), _result("q2"), _result("q3")],
    )


def _grade(score: float, metrics: dict[str, float] | None = None) -> sf.Grade:
    return sf.Grade(score=score, metrics=metrics or {}, coverage=1.0)


def _paired_grades() -> sf.Grades:
    failure = sf.GradeFailure(
        "q3",
        "member_2",
        "incomplete_verdicts",
        "one verdict is unresolved",
    )
    invalid = sf.Grade(
        score=None,
        metrics={},
        coverage=0.0,
        failure=failure,
    )
    return sf.Grades(
        run=_run(),
        results=[
            sf.CaseGrades(
                "q1",
                fusion=_grade(0.8, {"pass_rate": 0.8, "fusion_only": 0.4}),
                members={
                    "member_1": _grade(0.6, {"quality": 0.4}),
                    "member_2": _grade(0.7, {"quality": 0.9}),
                },
            ),
            sf.CaseGrades(
                "q2",
                fusion=_grade(1.0, {"pass_rate": 0.6}),
                members={
                    "member_1": _grade(0.4, {"quality": 0.6}),
                    "member_2": _grade(0.9),
                },
            ),
            sf.CaseGrades(
                "q3",
                fusion=_grade(1.0, {"pass_rate": 1.0, "fusion_only": 1.0}),
                members={
                    "member_1": _grade(1.0, {"quality": 1.0}),
                    "member_2": invalid,
                },
            ),
        ],
    )


def test_mean_uses_one_strict_paired_set_and_preserves_failures() -> None:
    grades = _paired_grades()

    report = grades.aggregate()

    assert report.benchmark_id == "paired@1"
    assert report.fusion_name == "paired-fusion"
    assert report.fusion_url4 == "(recipe)"
    assert report.n_cases == 3
    assert report.n_scored == 2
    assert report.coverage == pytest.approx(2 / 3)
    assert report.score == pytest.approx(0.9)
    assert report.baseline == pytest.approx(0.8)
    assert report.gain == pytest.approx(0.1)
    assert report.metrics == {"pass_rate": pytest.approx(0.7)}
    assert report.members["member_1"].model == "worker/one"
    assert report.members["member_1"].score == pytest.approx(0.5)
    assert report.members["member_1"].metrics == {"quality": pytest.approx(0.5)}
    assert report.members["member_2"].score == pytest.approx(0.8)
    assert report.members["member_2"].metrics == {}
    assert report.failures == grades.failures
    assert report.complete is False


def test_report_values_are_immutable_and_json_compatible() -> None:
    report = _paired_grades().aggregate()

    assert isinstance(report.members, Mapping)
    assert isinstance(report.metrics, Mapping)
    with pytest.raises(TypeError):
        report.members["member_1"] = report.members["member_1"]  # type: ignore[index]
    with pytest.raises(TypeError):
        report.metrics["other"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        report.members["member_1"].metrics["other"] = 1.0  # type: ignore[index]
    with pytest.raises(AttributeError):
        report.score = 0.0  # type: ignore[misc]
    assert json.loads(json.dumps(report.to_dict())) == report.to_dict()
    assert report.to_dict()["fusion_name"] == "paired-fusion"
    wire_members = report.to_dict()["members"]
    assert isinstance(wire_members, dict)
    assert tuple(wire_members) == ("member_1", "member_2")


def test_no_paired_cases_retains_every_member_without_fabricating_scores() -> None:
    benchmark = _benchmark()
    first = sf.RunFailure("q1", "timeout", "first failed")
    second = sf.RunFailure("q2", "url4", "second failed", status=502, code="failed")
    third = sf.RunFailure("q3", "connection", "third failed")
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="all-failed",
        fusion_url4="(recipe)",
        members=MEMBERS,
        cases=benchmark._materialize_cases(),
        results=[
            sf.CaseResult("q1", members={}, answer=None, failure=first),
            sf.CaseResult("q2", members={}, answer=None, failure=second),
            sf.CaseResult("q3", members={}, answer=None, failure=third),
        ],
    )
    grades = sf.Grades(
        run=run,
        results=[
            sf.CaseGrades("q1", fusion=None, members={}, run_failure=first),
            sf.CaseGrades("q2", fusion=None, members={}, run_failure=second),
            sf.CaseGrades("q3", fusion=None, members={}, run_failure=third),
        ],
    )

    report = grades.aggregate()

    assert grades.members == MEMBERS
    assert report.n_scored == 0
    assert report.coverage == 0.0
    assert report.score is None
    assert report.baseline is None
    assert report.gain is None
    assert report.metrics == {}
    assert tuple(report.members) == ("member_1", "member_2")
    assert all(member.score is None and not member.metrics for member in report.members.values())
    assert report.failures == (first, second, third)
    assert report.complete is False


def test_unsupported_aggregator_fails_without_fallback() -> None:
    class OtherAggregator(sf.Aggregator):
        kind = "other"

    benchmark = _benchmark(aggregator=OtherAggregator())
    grades = sf.Grades(
        run=_run(benchmark),
        results=[
            sf.CaseGrades(
                case_id,
                fusion=_grade(1.0),
                members={"member_1": _grade(1.0), "member_2": _grade(1.0)},
            )
            for case_id in ("q1", "q2", "q3")
        ],
    )

    with pytest.raises(TypeError, match="unsupported aggregator"):
        grades.aggregate()
    with pytest.raises(TypeError, match="sf.Grades"):
        _aggregation.aggregate_grades(None)  # type: ignore[arg-type]


def test_fusion_evaluate_delegates_to_the_union_preflight_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grades = _paired_grades()
    calls: list[tuple[object, int | None]] = []

    def fake_evaluate(
        _fusion: sf.Fusion,
        benchmark: str | sf.Benchmark,
        *,
        first: int | None = None,
        progress: bool | None = None,
    ) -> sf.Report:
        assert progress is None
        calls.append((benchmark, first))
        return grades.aggregate()

    monkeypatch.setattr(_execution, "evaluate_fusion", fake_evaluate)
    fusion = sf.Fusion(
        "paired-fusion",
        ["worker/one", "worker/two"],
        reducer=sf.reducers.MajorityVote(),
    )

    report = fusion.evaluate("paired@1", first=3)

    assert calls == [("paired@1", 3)]
    assert report == grades.aggregate()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"n_cases": 0}, "positive"),
        ({"n_scored": 4}, "cannot exceed"),
        ({"coverage": 0.5}, "n_scored / n_cases"),
        ({"baseline": 0.7}, "best member"),
        ({"gain": 0.0}, "score - baseline"),
    ],
)
def test_report_rejects_inconsistent_summary_state(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "benchmark_id": "paired@1",
        "fusion_name": "paired-fusion",
        "fusion_url4": "(recipe)",
        "n_cases": 3,
        "n_scored": 3,
        "coverage": 1.0,
        "score": 0.8,
        "baseline": 0.6,
        "gain": 0.2,
        "members": {
            "member_1": sf.MemberReport(model="one", score=0.6, metrics={}),
            "member_2": sf.MemberReport(model="two", score=0.5, metrics={}),
        },
        "metrics": {},
        "failures": (),
    }
    values.update(kwargs)

    with pytest.raises((TypeError, ValueError), match=message):
        sf.Report(**values)  # type: ignore[arg-type]
