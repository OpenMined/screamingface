"""DRACO partial results preserve the operational failure attached to each Case."""

from __future__ import annotations

import json

from url4_cloud.benchmarks.draco import aggregate as agg
from url4_cloud.benchmarks.draco.case_evaluation import (
    bind_case_evaluation,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA
from url4_cloud.benchmarks.errors import ProviderRefusal

_RUBRIC = {
    "sections": [
        {"id": "correctness", "criteria": [{"id": "c1", "weight": 1}]},
    ]
}


def _scored_row(case_id: int) -> dict[str, object]:
    raw_output = json.dumps({"explanation": "fixture verdict", "criterion_status": "MET"})
    records = [
        {
            "schema": CASE_SCHEMA,
            "case_id": case_id,
            "input": f"Question {case_id}",
            "output": f"Answer {case_id}",
            "finish_reason": "stop",
            "metadata": {},
        },
        {
            "schema": CHECK_SCHEMA,
            "case_id": case_id,
            "criterion_id": "c1",
            "criterion_type": "positive",
            "requirement": "Correct",
        },
        {
            "schema": agg.VERDICT_SCHEMA,
            "case_id": case_id,
            "criterion_id": "c1",
            "sequence": 1,
            "producer_type": "model",
            "producer_id": "fixture-judge",
            "criterion_status": "MET",
            "valid": True,
            "explanation": "fixture verdict",
            "raw_output": raw_output,
        },
    ]
    return bind_case_evaluation(
        case_id,
        [bind_criterion_evaluation(case_id, records[0], records[1], [records[2]])],
    )


def _selected(*case_ids: int) -> list[dict[str, object]]:
    return [{"id": case_id, "input": f"Question {case_id}"} for case_id in case_ids]


def test_partial_result_preserves_the_collected_case_error() -> None:
    rows = json.dumps(
        [
            _scored_row(1),
            {
                "error": {
                    "kind": "ResolutionError",
                    "code": "provider_error",
                    "message": "provider request failed",
                }
            },
        ]
    )

    result = agg.aggregate(
        rows,
        {1: _RUBRIC, 2: _RUBRIC},
        "draco",
        selected_cases=_selected(1, 2),
        judge_passes=1,
    )

    assert result["case_count"] == 2
    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["cases"][0]["grade"]["score"] == 1.0
    expected_failure = [
        {
            "stage": "candidate",
            "code": "provider_error",
            "message": "provider request failed",
            "retryable": None,
            "case_id": 2,
            "metadata": {"row_index": 1, "error_kind": "ResolutionError"},
        }
    ]
    assert result["failures"] == []
    assert result["cases"][1] == {
        "status": "failed",
        "case_id": 2,
        "input": "Question 2",
        "output": None,
        "finish_reason": None,
        "refusal": None,
        "grade": None,
        "failures": expected_failure,
        "metadata": {},
    }


def test_a_missing_selected_row_is_retained_and_invalidates_the_score() -> None:
    result = agg.aggregate(
        json.dumps([_scored_row(1)]),
        {1: _RUBRIC, 2: _RUBRIC},
        "draco",
        selected_cases=_selected(1, 2),
        judge_passes=1,
    )

    assert result["score"] is None
    assert [case["case_id"] for case in result["cases"]] == [1, 2]
    assert result["cases"][1]["failures"][0]["code"] == "case_result_missing"


def test_provider_refusal_is_retained_exactly_and_skips_grading() -> None:
    exact = "I can’t answer that request."
    result = agg.aggregate(
        json.dumps(
            [
                {
                    "error": {
                        "kind": "ProviderRefusal",
                        "message": str(ProviderRefusal(exact, finish_reason="content_filter")),
                    }
                }
            ]
        ),
        {1: _RUBRIC},
        "draco",
        selected_cases=_selected(1),
        judge_passes=1,
    )

    case = result["cases"][0]
    assert result["score"] is None
    assert result["metrics"] == {}
    assert case["status"] == "refused"
    assert case["refusal"] == exact
    assert case["finish_reason"] == "content_filter"
    assert case["grade"] is None
    assert case["failures"][0]["code"] == "provider_refusal"


def test_missing_selected_case_rubric_retains_the_case_and_invalidates_the_score() -> None:
    result = agg.aggregate(
        json.dumps([_scored_row(1), _scored_row(2)]),
        {1: _RUBRIC},
        "draco",
        selected_cases=_selected(1, 2),
        judge_passes=1,
    )

    assert result["case_count"] == 2
    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["cases"][0]["grade"]["score"] == 1.0
    assert result["cases"][1] == {
        "status": "failed",
        "case_id": 2,
        "input": "Question 2",
        "output": "Answer 2",
        "finish_reason": "stop",
        "refusal": None,
        "grade": None,
        "failures": [
            {
                "stage": "grading",
                "code": "missing_case_rubric",
                "message": "the selected Case has no installed DRACO rubric",
                "retryable": None,
                "case_id": 2,
                "metadata": {"row_index": 1},
            }
        ],
        "metadata": {},
    }


def test_nested_draco_records_are_not_discovered_as_a_case_evaluation() -> None:
    rows = json.dumps([{"nested": {"records": _scored_row(1)}}])

    result = agg.aggregate(
        rows,
        {1: _RUBRIC},
        "draco",
        selected_cases=_selected(1),
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None
    failure = result["cases"][0]["failures"][0]
    assert failure["code"] == "invalid_case_evaluation"
    assert failure["metadata"]["reason"] == "invalid DRACO Case Evaluation envelope"


def test_invalid_judge_evidence_is_retained_under_an_unscored_grade() -> None:
    case = {
        "schema": CASE_SCHEMA,
        "case_id": 1,
        "input": "Question 1",
        "output": "Answer 1",
        "finish_reason": "stop",
        "metadata": {},
    }
    check = {
        "schema": CHECK_SCHEMA,
        "case_id": 1,
        "criterion_id": "c1",
        "criterion_type": "positive",
        "requirement": "Correct",
    }
    invalid = {
        "schema": agg.VERDICT_SCHEMA,
        "case_id": 1,
        "criterion_id": "c1",
        "sequence": 1,
        "producer_type": "model",
        "producer_id": "fixture-judge",
        "valid": False,
        "reason": "invalid_json",
        "raw_output": "not json",
    }
    row = bind_case_evaluation(
        1,
        [bind_criterion_evaluation(1, case, check, [invalid])],
    )

    result = agg.aggregate(
        json.dumps([row]),
        {1: _RUBRIC},
        "draco",
        selected_cases=_selected(1),
        judge_passes=1,
    )

    grade = result["cases"][0]["grade"]
    assert result["score"] is None
    assert grade["score"] is None
    assert grade["checks"][0]["evidence"] == [
        {
            "sequence": 1,
            "producer": {"type": "model", "id": "fixture-judge"},
            "valid": False,
            "raw_output": "not json",
            "metadata": {"rejection_reason": "invalid_json"},
        }
    ]
    assert result["cases"][0]["failures"][0]["code"] == "no_valid_judge_verdict"


def test_a_row_claiming_another_selected_case_is_retained_as_unscored() -> None:
    rows = json.dumps([_scored_row(1), _scored_row(1)])

    result = agg.aggregate(
        rows,
        {1: _RUBRIC, 2: _RUBRIC},
        "draco",
        selected_cases=_selected(1, 2),
        judge_passes=1,
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"]["score"] == 1.0
    assert result["cases"][1]["grade"] is None


def test_one_row_cannot_mix_verdicts_from_different_cases() -> None:
    row = _scored_row(1)
    foreign = _scored_row(2)
    evidence = row["evidence"]
    foreign_evidence = foreign["evidence"]
    assert isinstance(evidence, list)
    assert isinstance(foreign_evidence, list)
    evidence.append(foreign_evidence[0])
    rows = json.dumps([row])

    result = agg.aggregate(
        rows,
        {1: _RUBRIC, 2: _RUBRIC},
        "draco",
        selected_cases=_selected(1),
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None
