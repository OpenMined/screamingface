"""OME-694 Client coverage and graded-refusal contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from math import inf, nan

import pytest

import screamingface as sf
from screamingface._evaluation.results import _case_result

_NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
_BENCHMARK = sf.BenchmarkInfo("ifeval", "revision-1", 1)
_OPERATION = sf.OperationInfo(id="op", kind="model", label="answer", depends_on=())


def _grade(score: float | None) -> sf.CaseGrade:
    return sf.CaseGrade(method="deterministic", score=score, metrics={}, checks=())


def _scored_case() -> sf.CaseResult:
    return sf.CaseResult(
        case_id=1,
        input="Follow this instruction.",
        output="Done.",
        finish_reason="stop",
        grade=_grade(1.0),
        failures=(),
        metadata={},
    )


def _candidate(
    *,
    coverage: float,
    metrics: dict[str, object] | None = None,
    failures: tuple[sf.Failure, ...] = (),
) -> sf.CandidateResult:
    return sf.CandidateResult(
        benchmark=_BENCHMARK,
        run_id="run-1",
        started_at=_NOW,
        completed_at=_NOW,
        name="model",
        kind="model",
        url4="(/openrouter/example/model)!''",
        models=("openrouter/example/model",),
        operations=(_OPERATION,),
        score=1.0,
        coverage=coverage,
        metrics={} if metrics is None else metrics,
        cases=(_scored_case(),),
        members=(),
        failures=failures,
        usage=sf.Usage(),
    )


def test_candidate_coverage_is_a_required_exported_top_level_value() -> None:
    result = _candidate(coverage=0.5)

    assert result.coverage == 0.5
    assert result.to_dict()["coverage"] == 0.5


@pytest.mark.parametrize("coverage", [-0.1, 1.1, nan, inf, True])
def test_candidate_coverage_rejects_values_outside_the_wire_contract(
    coverage: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="coverage"):
        _candidate(coverage=coverage)  # type: ignore[arg-type]


def test_candidate_metrics_cannot_duplicate_top_level_coverage() -> None:
    with pytest.raises(ValueError, match="coverage"):
        _candidate(coverage=1.0, metrics={"coverage": 1.0})


def test_a_scored_candidate_can_retain_a_safe_candidate_failure() -> None:
    failure = sf.Failure(
        stage="aggregation",
        code="partial_result",
        message="one selected Case could not be graded",
        operation_id="op",
    )

    result = _candidate(coverage=0.5, failures=(failure,))

    assert result.score == 1.0
    assert result.failures == (failure,)


def test_a_refusal_is_normally_graded_without_a_synthetic_failure() -> None:
    payload = {
        "status": "refused",
        "case_id": 1,
        "input": "A clinical question",
        "output": None,
        "finish_reason": "content_filter",
        "refusal": "I cannot answer that request.",
        "grade": {
            "method": "deterministic",
            "score": 0.0,
            "metrics": {},
            "checks": [],
        },
        "failures": [],
        "metadata": {},
    }

    case = _case_result(payload)

    assert case.status == "refused"
    assert case.grade is not None
    assert case.grade.score == 0.0
    assert case.failures == ()
    assert case.to_dict() == payload


def test_a_refusal_whose_grading_failed_retains_only_grading_failures() -> None:
    payload = {
        "status": "refused",
        "case_id": 1,
        "input": "A clinical question",
        "output": None,
        "finish_reason": "content_filter",
        "refusal": "I cannot answer that request.",
        "grade": {
            "method": "deterministic",
            "score": None,
            "metrics": {},
            "checks": [],
        },
        "failures": [
            {
                "stage": "grading",
                "code": "checker_failed",
                "message": "the checker failed",
                "retryable": False,
                "case_id": 1,
                "metadata": {},
            }
        ],
        "metadata": {},
    }

    case = _case_result(payload)

    assert case.status == "refused"
    assert case.grade is not None
    assert case.grade.score is None
    assert tuple(failure.stage for failure in case.failures) == ("grading",)
    assert case.to_dict() == payload
