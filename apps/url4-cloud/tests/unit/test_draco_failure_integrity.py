"""DRACO partial results preserve the operational failure attached to each Case."""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.draco import aggregate as agg

_RUBRIC = {
    "sections": [
        {"id": "correctness", "criteria": [{"id": "c1", "weight": 1}]},
    ]
}


def _scored_row(case_id: int) -> str:
    return json.dumps(
        {
            "schema": agg.VERDICT_SCHEMA,
            "case_id": case_id,
            "criterion_id": "c1",
            "criterion_status": "MET",
            "valid": True,
            "explanation": "fixture verdict",
        }
    )


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

    result = agg.aggregate(rows, {1: _RUBRIC, 2: _RUBRIC}, "draco")

    assert result["case_count"] == 1
    assert result["failures"] == [
        {
            "index": 1,
            "case_id": 2,
            "reason": "Candidate Case execution failed",
            "error": {
                "kind": "ResolutionError",
                "code": "provider_refusal",
                "message": "provider refused the request",
            },
        }
    ]


def test_two_rows_cannot_claim_the_same_case() -> None:
    rows = json.dumps([_scored_row(1), _scored_row(1)])

    with pytest.raises(agg.AggregateError, match="duplicate case_id"):
        agg.aggregate(rows, {1: _RUBRIC, 2: _RUBRIC}, "draco")


def test_one_row_cannot_mix_verdicts_from_different_cases() -> None:
    rows = json.dumps(["\n".join((_scored_row(1), _scored_row(2)))])

    with pytest.raises(agg.AggregateError, match="multiple case_id"):
        agg.aggregate(rows, {1: _RUBRIC, 2: _RUBRIC}, "draco")
