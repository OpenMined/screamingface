from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest

import screamingface as sf
from screamingface.grades import GradeFailureKind


def _benchmark() -> sf.Benchmark:
    return sf.Benchmark(
        "gpqa@1",
        cases=[sf.Case("q1", "Question", reference="B")],
        grader=sf.graders.ExactChoice(),
    )


def _successful_run() -> sf.Run:
    benchmark = _benchmark()
    return sf.Run(
        benchmark=benchmark,
        recipe_name="frontier-trio",
        recipe_url4="(recipe)",
        members={
            "member_1": "codex/gpt-5.5",
            "member_2": "gemini/2.5-flash",
            "member_3": "claude/sonnet-4.6",
        },
        cases=benchmark._materialize_cases(),
        results=[
            sf.CaseResult(
                "q1",
                members={
                    "member_1": sf.MemberResult("codex/gpt-5.5", "A"),
                    "member_2": sf.MemberResult("gemini/2.5-flash", "B"),
                    "member_3": sf.MemberResult("claude/sonnet-4.6", "B"),
                },
                answer="B",
            )
        ],
    )


def _exact_grade(score: float) -> sf.Grade:
    return sf.Grade(score=score, metrics={}, coverage=1.0)


def test_valid_grade_is_immutable_and_defensively_owns_metrics() -> None:
    metrics = {"pass_rate": 0.75}
    grade = sf.Grade(score=0.8, metrics=metrics, coverage=1.0)
    metrics["pass_rate"] = 0.0

    assert isinstance(grade.metrics, Mapping)
    assert grade.metrics == {"pass_rate": 0.75}
    assert grade.verdicts == ()
    assert grade.failure is None
    assert grade.valid is True
    with pytest.raises(TypeError):
        grade.metrics["other"] = 0.2  # type: ignore[index]
    with pytest.raises(AttributeError):
        grade.score = 0.1  # type: ignore[misc]


def test_failed_verdict_and_grade_preserve_structured_evidence() -> None:
    detail = sf.GradeFailure(
        case_id="q1",
        target="recipe",
        kind="invalid_judge_output",
        message="judge response did not match the required schema",
        criterion_id="factual-1",
        pass_number=2,
        status=200,
        code="invalid_judge_output",
    )
    verdict = sf.CriterionVerdict(
        criterion_id="factual-1",
        section="factual_accuracy",
        requirement="Names the required fact.",
        weight=1.0,
        pass_number=2,
        status=None,
        explanation=None,
        raw_response="not json",
        failure=detail,
    )
    summary = sf.GradeFailure(
        case_id="q1",
        target="recipe",
        kind="incomplete_verdicts",
        message="1 of 1 rubric verdicts is unresolved",
    )
    grade = sf.Grade(
        score=None,
        metrics={},
        coverage=0.0,
        verdicts=[verdict],
        failure=summary,
    )

    assert grade.valid is False
    assert grade.score is None
    assert grade.verdicts == (verdict,)
    assert grade.verdicts[0].raw_response == "not json"


def test_successful_rubric_shaped_grade_and_grader_are_serializable() -> None:
    benchmark = sf.Benchmark(
        "rubric@1",
        cases=[sf.Case("q1", "Question", reference={"sections": []})],
        grader=sf.graders.Rubric(
            model="gemini/3.1-pro-preview",
            prompt="Judge the criterion.",
            passes=5,
            params={"temperature": 0.2, "reasoning": "low"},
        ),
    )
    run = sf.Run(
        benchmark=benchmark,
        recipe_name="research-duo",
        recipe_url4="(recipe)",
        members={
            "member_1": "codex/gpt-5.5",
            "member_2": "gemini/2.5-flash",
        },
        cases=benchmark._materialize_cases(),
        results=[
            sf.CaseResult(
                "q1",
                members={
                    "member_1": sf.MemberResult("codex/gpt-5.5", "answer one"),
                    "member_2": sf.MemberResult("gemini/2.5-flash", "answer two"),
                },
                answer="fusion answer",
            )
        ],
    )
    verdict = sf.CriterionVerdict(
        "criterion-1",
        "factual_accuracy",
        "Names the required fact.",
        1,
        1,
        "MET",
        "The fact is present.",
        '{"explanation":"The fact is present.","criterion_status":"MET"}',
    )
    grade = sf.Grade(
        score=1,
        metrics={"pass_rate": 1},
        coverage=1,
        verdicts=[verdict],
    )
    grades = sf.Grades(
        run=run,
        results=[
            sf.CaseGrades(
                "q1",
                recipe=grade,
                members={"member_1": grade, "member_2": grade},
            )
        ],
    )

    payload = grades.to_dict()
    assert payload["grader"] == {
        "type": "rubric",
        "model": "gemini/3.1-pro-preview",
        "prompt": "Judge the criterion.",
        "passes": 5,
        "params": {"temperature": 0.2, "reasoning": "low"},
    }
    assert payload["results"][0]["recipe"]["verdicts"] == [  # type: ignore[index]
        {
            "criterion_id": "criterion-1",
            "section": "factual_accuracy",
            "requirement": "Names the required fact.",
            "weight": 1.0,
            "pass_number": 1,
            "status": "MET",
            "explanation": "The fact is present.",
            "raw_response": ('{"explanation":"The fact is present.","criterion_status":"MET"}'),
            "failure": None,
        }
    ]


def test_grades_flatten_detailed_and_summary_grade_failures() -> None:
    run = _successful_run()
    detail = sf.GradeFailure(
        "q1",
        "recipe",
        "timeout",
        "judge request timed out",
        criterion_id="criterion-1",
        pass_number=1,
        status=504,
        code="timeout",
    )
    verdict = sf.CriterionVerdict(
        "criterion-1",
        "factual_accuracy",
        "Names the required fact.",
        1.0,
        1,
        None,
        None,
        None,
        detail,
    )
    summary = sf.GradeFailure(
        "q1", "recipe", "incomplete_verdicts", "1 of 1 verdicts is unresolved"
    )
    invalid = sf.Grade(
        score=None,
        metrics={},
        coverage=0.0,
        verdicts=[verdict],
        failure=summary,
    )
    grades = sf.Grades(
        run=run,
        results=[
            sf.CaseGrades(
                "q1",
                recipe=invalid,
                members={
                    "member_1": _exact_grade(0.0),
                    "member_2": _exact_grade(1.0),
                    "member_3": _exact_grade(1.0),
                },
            )
        ],
    )

    assert grades.failures == (detail, summary)
    assert grades.complete is False
    assert grades.to_dict()["failures"] == [detail._to_wire(), summary._to_wire()]


def test_grades_preserve_nested_targets_and_json_compatible_snapshot() -> None:
    run = _successful_run()
    case = sf.CaseGrades(
        "q1",
        recipe=_exact_grade(1.0),
        members={
            "member_1": _exact_grade(0.0),
            "member_2": _exact_grade(1.0),
            "member_3": _exact_grade(1.0),
        },
    )
    grades = sf.Grades(run=run, results=[case])

    assert grades.benchmark_id == "gpqa@1"
    assert grades.recipe_url4 == "(recipe)"
    assert grades.grader == sf.graders.ExactChoice()
    assert grades.case_ids == ("q1",)
    assert grades.results == (case,)
    assert grades.failures == ()
    assert grades.complete is True
    assert grades.results[0].recipe == _exact_grade(1.0)
    assert tuple(grades.results[0].members) == ("member_1", "member_2", "member_3")
    assert json.loads(json.dumps(grades.to_dict())) == grades.to_dict()
    assert grades.to_dict() == {
        "benchmark_id": "gpqa@1",
        "recipe_name": "frontier-trio",
        "recipe_url4": "(recipe)",
        "members": {
            "member_1": "codex/gpt-5.5",
            "member_2": "gemini/2.5-flash",
            "member_3": "claude/sonnet-4.6",
        },
        "grader": {"type": "exact_choice"},
        "case_ids": ["q1"],
        "results": [
            {
                "case_id": "q1",
                "recipe": {
                    "score": 1.0,
                    "metrics": {},
                    "coverage": 1.0,
                    "verdicts": [],
                    "failure": None,
                    "valid": True,
                },
                "members": {
                    "member_1": {
                        "score": 0.0,
                        "metrics": {},
                        "coverage": 1.0,
                        "verdicts": [],
                        "failure": None,
                        "valid": True,
                    },
                    "member_2": {
                        "score": 1.0,
                        "metrics": {},
                        "coverage": 1.0,
                        "verdicts": [],
                        "failure": None,
                        "valid": True,
                    },
                    "member_3": {
                        "score": 1.0,
                        "metrics": {},
                        "coverage": 1.0,
                        "verdicts": [],
                        "failure": None,
                        "valid": True,
                    },
                },
                "run_failure": None,
            }
        ],
        "failures": [],
        "complete": True,
    }


def test_failed_run_case_has_no_grades_and_remains_in_failures() -> None:
    benchmark = _benchmark()
    failure = sf.RunFailure("q1", "timeout", "URL4 engine evaluation timed out")
    run = sf.Run(
        benchmark=benchmark,
        recipe_name="frontier-trio",
        recipe_url4="(recipe)",
        members={
            "member_1": "codex/gpt-5.5",
            "member_2": "gemini/2.5-flash",
            "member_3": "claude/sonnet-4.6",
        },
        cases=benchmark._materialize_cases(),
        results=[sf.CaseResult("q1", members={}, answer=None, failure=failure)],
    )
    case = sf.CaseGrades("q1", recipe=None, members={}, run_failure=failure)
    grades = sf.Grades(run=run, results=[case])

    assert case.recipe is None
    assert case.members == {}
    assert grades.failures == (failure,)
    assert grades.complete is False


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.Grade(score=1.1, metrics={}, coverage=1.0), "score"),
        (lambda: sf.Grade(score=1.0, metrics={}, coverage=0.5), "coverage"),
        (lambda: sf.Grade(score=None, metrics={}, coverage=0.5), "score"),
        (lambda: sf.Grade(score=0.0, metrics={"bad": float("nan")}, coverage=1.0), "metric"),
        (
            lambda: sf.GradeFailure(
                "q1",
                "recipe",
                cast(GradeFailureKind, "wrong"),
                "message",
            ),
            "kind",
        ),
        (
            lambda: sf.GradeFailure(
                "q1",
                "recipe",
                "timeout",
                "message",
                criterion_id="criterion",
            ),
            "together",
        ),
        (
            lambda: sf.GradeFailure("q1", "recipe", "timeout", "message", status=99),
            "status",
        ),
        (
            lambda: sf.GradeFailure(
                "q1",
                "recipe",
                "timeout",
                "message",
                criterion_id="criterion",
                pass_number=0,
            ),
            "positive",
        ),
        (
            lambda: sf.CriterionVerdict(
                "criterion",
                "section",
                "requirement",
                0.0,
                1,
                "MET",
                "explanation",
                "raw",
            ),
            "weight",
        ),
        (
            lambda: sf.CriterionVerdict(
                "criterion", "section", "requirement", 1.0, 1, None, None, None
            ),
            "status",
        ),
        (
            lambda: sf.CriterionVerdict(
                "criterion", "section", "requirement", 1.0, 1, "MET", "", "raw"
            ),
            "explanation",
        ),
        (
            lambda: sf.CriterionVerdict(
                "criterion", "section", "requirement", 1.0, 1, "MET", "explanation", ""
            ),
            "raw response",
        ),
        (
            lambda: sf.CriterionVerdict(
                "criterion",
                "section",
                "requirement",
                1.0,
                1,
                None,
                None,
                None,
                cast(sf.GradeFailure, "wrong"),
            ),
            "sf.GradeFailure",
        ),
        (
            lambda: sf.CriterionVerdict(
                "criterion",
                "section",
                "requirement",
                1.0,
                1,
                "MET",
                "explanation",
                "raw",
                sf.GradeFailure(
                    "q1",
                    "recipe",
                    "timeout",
                    "late",
                    criterion_id="criterion",
                    pass_number=1,
                ),
            ),
            "status",
        ),
        (
            lambda: sf.Grade(
                score=1.0,
                metrics={},
                coverage=1.0,
                verdicts=cast(list[sf.CriterionVerdict], ["wrong"]),
            ),
            "verdicts",
        ),
        (
            lambda: sf.Grade(
                score=1.0,
                metrics={},
                coverage=1.0,
                failure=cast(sf.GradeFailure, "wrong"),
            ),
            "sf.GradeFailure",
        ),
        (
            lambda: sf.Grade(score="1", metrics={}, coverage=1.0),  # type: ignore[arg-type]
            "numeric",
        ),
        (
            lambda: sf.Grade(score=1.0, metrics=cast(dict[str, float], []), coverage=1.0),
            "mapping",
        ),
        (
            lambda: sf.Grade(
                score=0.5,
                metrics={},
                coverage=1.0,
                verdicts=[
                    sf.CriterionVerdict(
                        "criterion",
                        "section",
                        "requirement",
                        1.0,
                        1,
                        None,
                        None,
                        None,
                        sf.GradeFailure(
                            "q1",
                            "recipe",
                            "timeout",
                            "late",
                            criterion_id="criterion",
                            pass_number=1,
                        ),
                    )
                ],
            ),
            "coverage",
        ),
        (
            lambda: sf.Grade(
                score=0.5,
                metrics={},
                coverage=0.0,
                failure=sf.GradeFailure("q1", "recipe", "incomplete_verdicts", "incomplete"),
            ),
            "score",
        ),
        (
            lambda: sf.Grade(
                score=None,
                metrics={},
                coverage=1.0,
                failure=sf.GradeFailure("q1", "recipe", "incomplete_verdicts", "incomplete"),
            ),
            "complete coverage",
        ),
        (
            lambda: sf.Grade(
                score=None,
                metrics={"partial": 0.5},
                coverage=0.0,
                failure=sf.GradeFailure("q1", "recipe", "incomplete_verdicts", "incomplete"),
            ),
            "partial metrics",
        ),
        (
            lambda: sf.CaseGrades("q1", recipe=None, members={}),
            "Recipe",
        ),
        (
            lambda: sf.CaseGrades("q1", recipe=_exact_grade(1.0), members={}),
            "member grades",
        ),
        (
            lambda: sf.CaseGrades(
                "q1",
                recipe=None,
                members={},
                run_failure=cast(sf.RunFailure, "wrong"),
            ),
            "sf.RunFailure",
        ),
        (
            lambda: sf.CaseGrades(
                "q1",
                recipe=None,
                members={},
                run_failure=sf.RunFailure("other", "timeout", "late"),
            ),
            "IDs",
        ),
        (
            lambda: sf.CaseGrades(
                "q1",
                recipe=_exact_grade(1.0),
                members=cast(dict[str, sf.Grade], {"member_1": "wrong"}),
            ),
            "sf.Grade",
        ),
        (
            lambda: sf.CaseGrades(
                "q1",
                recipe=_exact_grade(1.0),
                members=[("member_1", _exact_grade(1.0)), ("member_1", _exact_grade(1.0))],
            ),
            "unique",
        ),
        (
            lambda: sf.CaseGrades(
                "q1",
                recipe=_exact_grade(1.0),
                members={},
                run_failure=sf.RunFailure("q1", "timeout", "late"),
            ),
            "failed",
        ),
    ],
)
def test_grading_values_reject_inconsistent_state(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_grades_require_the_exact_run_case_and_member_shape() -> None:
    run = _successful_run()
    wrong_members = sf.CaseGrades(
        "q1",
        recipe=_exact_grade(1.0),
        members={"member_1": _exact_grade(1.0)},
    )

    with pytest.raises(ValueError, match="member slots"):
        sf.Grades(run=run, results=[wrong_members])


def test_grades_reject_inconsistent_run_result_shapes_and_failure_identity() -> None:
    run = _successful_run()
    valid = sf.CaseGrades(
        "q1",
        recipe=_exact_grade(1.0),
        members={
            "member_1": _exact_grade(0.0),
            "member_2": _exact_grade(1.0),
            "member_3": _exact_grade(1.0),
        },
    )
    with pytest.raises(TypeError, match="sf.Run"):
        sf.Grades(run=cast(sf.Run, "wrong"), results=[valid])
    with pytest.raises(TypeError, match="sf.CaseGrades"):
        sf.Grades(run=run, results=cast(list[sf.CaseGrades], ["wrong"]))
    with pytest.raises(ValueError, match="case IDs"):
        sf.Grades(
            run=run,
            results=[
                sf.CaseGrades(
                    "other",
                    recipe=_exact_grade(1.0),
                    members={
                        "member_1": _exact_grade(0.0),
                        "member_2": _exact_grade(1.0),
                        "member_3": _exact_grade(1.0),
                    },
                )
            ],
        )

    wrong_summary = sf.GradeFailure("q1", "member_1", "incomplete_verdicts", "wrong target")
    invalid_fusion = sf.Grade(
        score=None,
        metrics={},
        coverage=0.0,
        failure=wrong_summary,
    )
    with pytest.raises(ValueError, match="identity"):
        sf.Grades(
            run=run,
            results=[
                sf.CaseGrades(
                    "q1",
                    recipe=invalid_fusion,
                    members={
                        "member_1": _exact_grade(0.0),
                        "member_2": _exact_grade(1.0),
                        "member_3": _exact_grade(1.0),
                    },
                )
            ],
        )
