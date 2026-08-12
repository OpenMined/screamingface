"""IFEval keeps failed Cases inspectable without publishing a partial score."""

from __future__ import annotations

import json

from url4_cloud.benchmarks.errors import ProviderRefusal
from url4_cloud.benchmarks.ifeval.aggregate import SCHEMA, aggregate, aggregate_corrective
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


def test_provider_refusal_is_retained_exactly_and_skips_grading() -> None:
    exact = "I can’t comply with that request."
    result = aggregate(
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
        _SPEC,
        "ifeval",
        _ORDER,
        selected_case_count=1,
    )

    case = result["cases"][0]
    assert result["score"] is None
    assert result["metrics"] == {}
    assert case["status"] == "refused"
    assert case["refusal"] == exact
    assert case["finish_reason"] == "content_filter"
    assert case["grade"] is None
    assert case["failures"][0]["code"] == "provider_refusal"


def test_nested_verifier_record_is_not_discovered_as_grading() -> None:
    payload = json.dumps([{"candidate_text": json.dumps(_valid_record())}])

    result = aggregate(payload, _SPEC, "ifeval", _ORDER, selected_case_count=1)

    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["cases"][0]["grade"] is None
    assert result["cases"][0]["failures"][0]["code"] == "invalid_case_evaluation"


def test_bare_check_record_is_not_a_case_evaluation_envelope() -> None:
    payload = json.dumps([_valid_record()])

    result = aggregate(payload, _SPEC, "ifeval", _ORDER, selected_case_count=1)

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None


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

    result = aggregate_corrective(
        payload,
        _SPEC,
        SELF_CORRECTIVE_ID,
        SELF_CORRECTIVE_REVISION,
        _ORDER,
        selected_case_count=1,
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None
    assert result["cases"][0]["failures"][0]["code"] == "invalid_case_evaluation"
