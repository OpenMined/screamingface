"""IFEval keeps failed Cases inspectable without publishing a partial score."""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.ifeval.aggregate import (
    SCHEMA,
    AggregateError,
    aggregate,
    aggregate_corrective,
)
from url4_cloud.benchmarks.ifeval.case_evaluation import bind_case_evaluation
from url4_cloud.benchmarks.ifeval.corrective_policy import (
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
)

_SPEC = {
    1: {
        "prompt": "Answer without commas.",
        "instruction_id_list": ["punctuation:no_comma"],
        "kwargs": [{}],
    }
}

# The installed selection order (cases.json file order) — row N binds to _ORDER[N].
_ORDER = [1]


def _valid_record() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "case_id": 1,
        "attempt": 1,
        "valid": True,
        "answer": "A compliant answer",
        "refusal": None,
        "finish_reason": "stop",
        "instruction_id_list": ["punctuation:no_comma"],
        "descriptions": ["Do not use commas."],
        "strict": [True],
        "loose": [True],
        "violations": [],
    }


def test_collected_candidate_failure_returns_a_complete_unscored_result() -> None:
    payload = json.dumps(
        [
            {
                "error": {
                    "kind": "ResolutionError",
                    "code": "provider_error",
                    "message": "the provider was unavailable",
                    "permanent": True,
                }
            }
        ]
    )

    result = aggregate(payload, _SPEC, "ifeval", _ORDER, selected_case_count=1)

    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["case_count"] == 1
    assert result["failures"] == []
    assert result["cases"] == [
        {
            "status": "failed",
            "case_id": 1,
            "input": "Answer without commas.",
            "output": None,
            "finish_reason": None,
            "refusal": None,
            "grade": None,
            "failures": [
                {
                    "stage": "candidate",
                    "code": "provider_error",
                    "message": "the provider was unavailable",
                    "retryable": False,
                    "case_id": 1,
                    "metadata": {"error_kind": "ResolutionError", "row_index": 0},
                }
            ],
            "metadata": {},
        }
    ]


def test_provider_refusal_is_retained_exactly_and_graded_normally() -> None:
    exact = "I can’t comply with that request."
    record = _valid_record()
    record.update(
        {
            "answer": exact,
            "refusal": exact,
            "finish_reason": "content_filter",
            "strict": [False],
            "loose": [False],
            "violations": ["Do not use commas."],
        }
    )
    result = aggregate(
        json.dumps([bind_case_evaluation(1, [record])]),
        _SPEC,
        "ifeval",
        _ORDER,
        selected_case_count=1,
    )

    case = result["cases"][0]
    assert result["score"] == 0.0
    assert result["coverage"] == 1.0
    assert case["status"] == "refused"
    assert case["refusal"] == exact
    assert case["finish_reason"] == "content_filter"
    assert case["grade"]["score"] == 0.0
    assert case["failures"] == []


def test_nested_verifier_record_is_not_discovered_as_grading() -> None:
    payload = json.dumps([{"candidate_text": json.dumps(_valid_record())}])

    with pytest.raises(AggregateError, match="position 0"):
        aggregate(payload, _SPEC, "ifeval", _ORDER, selected_case_count=1)


def test_bare_check_record_is_not_a_case_evaluation_envelope() -> None:
    payload = json.dumps([_valid_record()])

    with pytest.raises(AggregateError, match="position 0"):
        aggregate(payload, _SPEC, "ifeval", _ORDER, selected_case_count=1)


def test_corrective_collected_failure_returns_a_complete_unscored_result() -> None:
    payload = json.dumps(
        [
            {
                "error": {
                    "kind": "ResolutionError",
                    "code": "provider_error",
                    "message": "the provider was unavailable",
                    "permanent": True,
                }
            }
        ]
    )

    result = aggregate_corrective(
        payload,
        _SPEC,
        SELF_CORRECTIVE_ID,
        SELF_CORRECTIVE_REVISION,
        _ORDER,
        selected_case_count=1,
    )

    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["case_count"] == 1
    assert result["cases"][0]["grade"] is None
    assert result["cases"][0]["failures"][0]["code"] == "provider_error"


def test_corrective_nested_check_is_not_discovered_as_grading() -> None:
    payload = json.dumps([{"nested": {"record": _valid_record()}}])

    with pytest.raises(AggregateError, match="position 0"):
        aggregate_corrective(
            payload,
            _SPEC,
            SELF_CORRECTIVE_ID,
            SELF_CORRECTIVE_REVISION,
            _ORDER,
            selected_case_count=1,
        )
