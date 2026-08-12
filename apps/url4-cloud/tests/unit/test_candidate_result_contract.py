"""Strict producer-side contracts for every Engine-owned Benchmark result."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from url4_cloud.benchmarks.contract import (
    CANDIDATE_RESULT_SCHEMA,
    CandidateResult,
    CaseGrade,
    CaseResult,
    Check,
    Evidence,
    EvidenceProducer,
    Failure,
)


def _evidence(**overrides: Any) -> Evidence:
    values: dict[str, Any] = {
        "sequence": 1,
        "producer": EvidenceProducer(type="deterministic", id="ifeval/official-verifier"),
        "valid": True,
        "outcome": "MET",
        "explanation": "the instruction was followed",
        "raw_output": True,
        "metadata": {},
    }
    values.update(overrides)
    return Evidence(**values)


def _check(**overrides: Any) -> Check:
    values: dict[str, Any] = {
        "type": "instruction",
        "id": "instruction-1",
        "label": "answer in JSON",
        "outcome": "MET",
        "score": 1.0,
        "evidence": [_evidence()],
        "metadata": {},
    }
    values.update(overrides)
    return Check(**values)


def _grade(**overrides: Any) -> CaseGrade:
    values: dict[str, Any] = {
        "method": "deterministic",
        "score": 1.0,
        "metrics": {"follow_all_strict": True},
        "checks": [_check()],
    }
    values.update(overrides)
    return CaseGrade(**values)


def _scored_case(case_id: int | str = 7, **overrides: Any) -> CaseResult:
    values: dict[str, Any] = {
        "status": "scored",
        "case_id": case_id,
        "input": "Return JSON.",
        "output": "{}",
        "finish_reason": "stop",
        "refusal": None,
        "grade": _grade(),
        "failures": [],
        "metadata": {},
    }
    values.update(overrides)
    return CaseResult(**values)


def _failure(**overrides: Any) -> Failure:
    values: dict[str, Any] = {
        "stage": "grading",
        "code": "judge_unavailable",
        "message": "the Judge did not return a usable verdict",
        "retryable": True,
        "case_id": 7,
        "metadata": {},
    }
    values.update(overrides)
    return Failure(**values)


def _candidate(**overrides: Any) -> CandidateResult:
    values: dict[str, Any] = {
        "benchmark_id": "ifeval",
        "benchmark_revision": "rev",
        "case_count": 1,
        "score": 1.0,
        "metrics": {"pass_rate": 1.0, "coverage": 1.0, "strict_accuracy": 1.0},
        "cases": [_scored_case()],
        "failures": [],
    }
    values.update(overrides)
    return CandidateResult(**values)


def test_scored_result_serializes_the_strict_v1_shape() -> None:
    payload = _candidate().as_payload()

    assert payload == {
        "schema": CANDIDATE_RESULT_SCHEMA,
        "benchmark_id": "ifeval",
        "benchmark_revision": "rev",
        "case_count": 1,
        "score": 1.0,
        "metrics": {"pass_rate": 1.0, "coverage": 1.0, "strict_accuracy": 1.0},
        "cases": [
            {
                "status": "scored",
                "case_id": 7,
                "input": "Return JSON.",
                "output": "{}",
                "finish_reason": "stop",
                "refusal": None,
                "grade": {
                    "method": "deterministic",
                    "score": 1.0,
                    "metrics": {"follow_all_strict": True},
                    "checks": [
                        {
                            "type": "instruction",
                            "id": "instruction-1",
                            "label": "answer in JSON",
                            "outcome": "MET",
                            "score": 1.0,
                            "evidence": [
                                {
                                    "sequence": 1,
                                    "producer": {
                                        "type": "deterministic",
                                        "id": "ifeval/official-verifier",
                                    },
                                    "valid": True,
                                    "outcome": "MET",
                                    "explanation": "the instruction was followed",
                                    "raw_output": True,
                                    "metadata": {},
                                }
                            ],
                            "metadata": {},
                        }
                    ],
                },
                "failures": [],
                "metadata": {},
            }
        ],
        "failures": [],
    }


def test_nested_contracts_forbid_unknown_fields() -> None:
    values = _check().model_dump()
    values["accidental"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Check(**values)


def test_structural_contract_fields_do_not_coerce_strings() -> None:
    with pytest.raises(ValidationError):
        _grade(score="1")
    with pytest.raises(ValidationError):
        _evidence(sequence="1")


def test_case_identity_is_a_non_blank_string_or_non_boolean_integer() -> None:
    assert _scored_case(case_id="official-case-A").case_id == "official-case-A"
    for invalid in (True, "", "  "):
        with pytest.raises(ValidationError, match="case_id"):
            _scored_case(case_id=invalid)  # type: ignore[arg-type]


def test_invalid_evidence_cannot_claim_an_outcome_or_explanation() -> None:
    with pytest.raises(ValidationError, match="invalid Evidence"):
        _evidence(valid=False)


def test_scored_case_requires_a_numeric_grade_and_no_failure_or_refusal() -> None:
    with pytest.raises(ValidationError, match="scored Case"):
        _scored_case(grade=_grade(score=None))
    with pytest.raises(ValidationError, match="scored Case"):
        _scored_case(failures=[_failure()])
    with pytest.raises(ValidationError, match="scored Case"):
        _scored_case(refusal="I cannot help with that")


def test_refused_case_preserves_exact_refusal_and_provider_failure() -> None:
    refusal = "I can’t provide that dosage."
    case = CaseResult(
        status="refused",
        case_id=7,
        input="Recommend a dosage.",
        output=None,
        finish_reason="content_filter",
        refusal=refusal,
        grade=None,
        failures=[
            _failure(
                stage="candidate",
                code="provider_refusal",
                message="the provider refused this Candidate request",
                retryable=False,
            )
        ],
        metadata={},
    )

    assert case.refusal == refusal
    assert case.failures[0].code == "provider_refusal"
    with pytest.raises(ValidationError, match="refused Case"):
        CaseResult(**{**case.model_dump(), "refusal": None})


def test_failed_case_requires_a_typed_failure_and_cannot_carry_a_score() -> None:
    case = CaseResult(
        status="failed",
        case_id=7,
        input="Return JSON.",
        output="not json",
        finish_reason="stop",
        refusal=None,
        grade=_grade(score=None),
        failures=[_failure()],
        metadata={},
    )
    assert case.grade is not None and case.grade.score is None

    with pytest.raises(ValidationError, match="failed Case"):
        CaseResult(**{**case.model_dump(), "failures": []})
    with pytest.raises(ValidationError, match="failed Case"):
        CaseResult(**{**case.model_dump(), "grade": _grade()})


def test_candidate_rejects_duplicate_case_identity() -> None:
    with pytest.raises(ValidationError, match="duplicate case_id"):
        _candidate(case_count=2, cases=[_scored_case(7), _scored_case(7)])


def test_case_failures_must_belong_to_that_case() -> None:
    with pytest.raises(ValidationError, match="must reference its own case_id"):
        CaseResult(
            status="failed",
            case_id=7,
            input=None,
            output=None,
            finish_reason=None,
            refusal=None,
            grade=None,
            failures=[_failure(case_id=8)],
            metadata={},
        )


def test_candidate_level_failures_must_not_claim_a_case() -> None:
    with pytest.raises(ValidationError, match="Candidate-level Failure"):
        _candidate(
            score=None,
            metrics={},
            failures=[_failure(stage="aggregation")],
        )


def test_candidate_requires_exact_case_count_and_canonical_scored_metrics() -> None:
    with pytest.raises(ValidationError, match="case_count"):
        _candidate(case_count=2)
    for missing in ("pass_rate", "coverage"):
        metrics = {"pass_rate": 1.0, "coverage": 1.0}
        del metrics[missing]
        with pytest.raises(ValidationError, match=missing):
            _candidate(metrics=metrics)


def test_unscored_candidate_cannot_publish_plausible_partial_metrics() -> None:
    failed = CaseResult(
        status="failed",
        case_id=7,
        input="Return JSON.",
        output=None,
        finish_reason=None,
        refusal=None,
        grade=None,
        failures=[_failure()],
        metadata={},
    )
    assert _candidate(score=None, metrics={}, cases=[failed]).score is None

    with pytest.raises(ValidationError, match="unscored"):
        _candidate(score=None, cases=[failed])


def test_unscored_candidate_requires_an_explicit_failure_or_non_scored_case() -> None:
    with pytest.raises(ValidationError, match="must be explained"):
        _candidate(score=None, metrics={})


def test_candidate_score_is_unscored_when_any_case_is_not_scored() -> None:
    failed = CaseResult(
        status="failed",
        case_id=7,
        input=None,
        output=None,
        finish_reason=None,
        refusal=None,
        grade=None,
        failures=[_failure()],
        metadata={},
    )
    with pytest.raises(ValidationError, match="non-scored Case"):
        _candidate(cases=[failed])


def test_healthbench_negative_score_remains_valid() -> None:
    assert _candidate(score=-3.0).score == -3.0
    with pytest.raises(ValidationError):
        _candidate(score=1.5)


@pytest.mark.parametrize("score", (True, float("nan"), float("inf")))
def test_scores_reject_booleans_and_non_finite_values(score: object) -> None:
    with pytest.raises(ValidationError):
        _candidate(score=score)
