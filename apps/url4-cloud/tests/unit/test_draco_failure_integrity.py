"""DRACO partial results preserve the operational failure attached to each Case."""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.draco import aggregate as agg
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA

_RUBRIC = {
    "sections": [
        {"id": "correctness", "criteria": [{"id": "c1", "weight": 1}]},
    ]
}


def _scored_row(case_id: int) -> str:
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
    return "\n".join(map(json.dumps, records))


def _selected(*case_ids: int) -> list[dict[str, object]]:
    return [{"id": case_id, "input": f"Question {case_id}"} for case_id in case_ids]


def test_partial_result_preserves_the_collected_case_error() -> None:
    rows = json.dumps(
        [
            _scored_row(1),
            {
                "error": {
                    "kind": "ResolutionError",
                    "code": "provider_refusal",
                    "message": "provider refused the request",
                }
            },
        ]
    )

    result = agg.aggregate(
        rows,
        {1: _RUBRIC, 2: _RUBRIC},
        "draco",
        selected_cases=_selected(1, 2),
    )

    assert result["case_count"] == 2
    expected_failure = [
        {
            "stage": "candidate",
            "code": "provider_refusal",
            "message": "provider refused the request",
            "retryable": None,
            "case_id": 2,
            "metadata": {"row_index": 1, "error_kind": "ResolutionError"},
        }
    ]
    assert result["failures"] == []
    assert result["cases"][1] == {
        "case_id": 2,
        "input": "Question 2",
        "output": None,
        "finish_reason": None,
        "grade": None,
        "failures": expected_failure,
        "metadata": {},
    }


def test_two_rows_cannot_claim_the_same_case() -> None:
    rows = json.dumps([_scored_row(1), _scored_row(1)])

    with pytest.raises(agg.AggregateError, match="duplicate case_id"):
        agg.aggregate(
            rows,
            {1: _RUBRIC, 2: _RUBRIC},
            "draco",
            selected_cases=_selected(1, 2),
        )


def test_one_row_cannot_mix_verdicts_from_different_cases() -> None:
    foreign_verdict = agg.harvest_verdicts(_scored_row(2))[0]
    rows = json.dumps([_scored_row(1) + "\n" + json.dumps(foreign_verdict)])

    with pytest.raises(agg.AggregateError, match="multiple case_id"):
        agg.aggregate(
            rows,
            {1: _RUBRIC, 2: _RUBRIC},
            "draco",
            selected_cases=_selected(1),
        )
