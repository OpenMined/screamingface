"""Benchmark-neutral, immutable Case Results retain complete grading evidence."""

from __future__ import annotations

import pytest

import screamingface as sf


def _graded_case() -> sf.CaseResult:
    raw = '{"explanation":"The response states four.","criterion_status":"MET"}'
    return sf.CaseResult(
        case_id=1,
        input="What is two plus two?",
        output="Four.",
        finish_reason="stop",
        grade=sf.CaseGrade(
            method="rubric",
            score=1.0,
            metrics={"coverage": 1.0, "axis_scores": {"correctness": 1.0}},
            checks=(
                sf.Check(
                    type="criterion",
                    id="correct",
                    label="States that two plus two is four",
                    evidence=(
                        sf.Evidence(
                            sequence=1,
                            producer=sf.EvidenceProducer(
                                type="model", id="openrouter/google/gemini-3.1-pro-preview"
                            ),
                            valid=True,
                            outcome="MET",
                            explanation="The response states four.",
                            raw_output=raw,
                            metadata={},
                        ),
                    ),
                    metadata={"criterion_type": "positive", "weight": 1, "axis": "correctness"},
                ),
            ),
        ),
        failures=(),
        metadata={"domain": "Arithmetic", "tags": ["smoke"]},
    )


def test_case_result_serializes_every_observed_fact_losslessly() -> None:
    case = _graded_case()

    assert case.to_dict() == {
        "case_id": 1,
        "input": "What is two plus two?",
        "output": "Four.",
        "finish_reason": "stop",
        "grade": {
            "method": "rubric",
            "score": 1.0,
            "metrics": {"coverage": 1.0, "axis_scores": {"correctness": 1.0}},
            "checks": [
                {
                    "type": "criterion",
                    "id": "correct",
                    "label": "States that two plus two is four",
                    "evidence": [
                        {
                            "sequence": 1,
                            "producer": {
                                "type": "model",
                                "id": "openrouter/google/gemini-3.1-pro-preview",
                            },
                            "valid": True,
                            "outcome": "MET",
                            "explanation": "The response states four.",
                            "raw_output": (
                                '{"explanation":"The response states four.",'
                                '"criterion_status":"MET"}'
                            ),
                            "metadata": {},
                        }
                    ],
                    "metadata": {
                        "criterion_type": "positive",
                        "weight": 1,
                        "axis": "correctness",
                    },
                }
            ],
        },
        "failures": [],
        "metadata": {"domain": "Arithmetic", "tags": ["smoke"]},
    }


def test_case_result_recursively_freezes_benchmark_metadata() -> None:
    case = _graded_case()

    with pytest.raises(TypeError):
        case.metadata["domain"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        case.grade.metrics["coverage"] = 0.0  # type: ignore[index,union-attr]
    assert case.metadata["tags"] == ("smoke",)


def test_failed_case_retains_the_failure_without_fabricating_an_output_or_grade() -> None:
    failure = sf.Failure(
        stage="candidate",
        code="provider_refusal",
        message="provider refused the request",
        retryable=None,
        case_id=2,
        metadata={"error_kind": "ResolutionError"},
    )

    case = sf.CaseResult(
        case_id=2,
        input="A clinical question",
        output=None,
        finish_reason=None,
        grade=None,
        failures=(failure,),
        metadata={"domain": "Medicine"},
    )

    assert case.to_dict()["failures"] == [
        {
            "stage": "candidate",
            "code": "provider_refusal",
            "message": "provider refused the request",
            "case_id": 2,
            "metadata": {"error_kind": "ResolutionError"},
        }
    ]


def test_invalid_evidence_keeps_exact_raw_output_and_rejection_reason() -> None:
    evidence = sf.Evidence(
        sequence=2,
        producer=sf.EvidenceProducer(type="model", id="provider/judge"),
        valid=False,
        raw_output="not json",
        metadata={"rejection_reason": "invalid_json"},
    )

    assert evidence.to_dict() == {
        "sequence": 2,
        "producer": {"type": "model", "id": "provider/judge"},
        "valid": False,
        "raw_output": "not json",
        "metadata": {"rejection_reason": "invalid_json"},
    }
