"""Canonical IFEval rows must carry the verifier record for their selected Case."""

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
from url4_cloud.benchmarks.ifeval.iterative_correction import SELF_CORRECTIVE_REVISION

_SPECS = {
    1: {"prompt": "No commas.", "instruction_id_list": ["punctuation:no_comma"]},
    2: {"prompt": "Use quotes.", "instruction_id_list": ["startend:quotation"]},
}

# The installed selection order (cases.json file order) — row N binds to _ORDER[N].
_ORDER = [1, 2]


def _record(case_id: int) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "attempt": 1,
        "valid": True,
        "answer": f"Answer {case_id}",
        "refusal": None,
        "finish_reason": "stop",
        "instruction_id_list": _SPECS[case_id]["instruction_id_list"],
        "descriptions": ["Fixture instruction"],
        "strict": [True],
        "loose": [True],
        "violations": [],
    }


def _evaluation(case_id: int) -> dict[str, object]:
    return bind_case_evaluation(case_id, [_record(case_id)])


def test_swapped_known_case_records_cannot_publish_a_score() -> None:
    """A real record is still invalid when it belongs to the other selected row."""

    rows = json.dumps([_evaluation(2), _evaluation(1)])

    with pytest.raises(AggregateError, match="position 0"):
        aggregate(rows, _SPECS, "ifeval", _ORDER, selected_case_count=2)


@pytest.mark.parametrize(
    ("reducer", "extra"),
    [
        (aggregate, (_ORDER,)),
        (aggregate_corrective, (SELF_CORRECTIVE_REVISION, _ORDER)),
    ],
)
def test_zero_row_ifeval_payloads_retain_the_selected_cases(reducer, extra) -> None:
    result = reducer("[]", _SPECS, "ifeval", *extra, selected_case_count=2)

    assert result["score"] is None
    assert [case["failures"][0]["code"] for case in result["cases"]] == [
        "case_result_missing",
        "case_result_missing",
    ]


def test_truthy_text_cannot_impersonate_verifier_booleans() -> None:
    forged = _record(1)
    forged["strict"] = ["false"]
    rows = json.dumps(
        [
            bind_case_evaluation(1, [forged]),
            _evaluation(2),
        ]
    )

    with pytest.raises(AggregateError, match="position 0"):
        aggregate(rows, _SPECS, "ifeval", _ORDER, selected_case_count=2)


def test_a_refusal_must_be_the_exact_text_checked_by_ifeval() -> None:
    forged = _record(1)
    forged["refusal"] = "provider refusal"
    rows = json.dumps([bind_case_evaluation(1, [forged]), _evaluation(2)])

    with pytest.raises(AggregateError, match="position 0"):
        aggregate(rows, _SPECS, "ifeval", _ORDER, selected_case_count=2)


def test_a_missing_selected_row_is_retained_and_lowers_coverage() -> None:
    rows = json.dumps([_evaluation(1)])

    result = aggregate(rows, _SPECS, "ifeval", _ORDER, selected_case_count=2)

    assert result["score"] == 1.0
    assert result["coverage"] == 0.5
    assert [case["case_id"] for case in result["cases"]] == [1, 2]
    assert result["cases"][1]["failures"][0]["code"] == "case_result_missing"
