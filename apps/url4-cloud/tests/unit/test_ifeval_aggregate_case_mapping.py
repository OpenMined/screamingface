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
from url4_cloud.benchmarks.ifeval.iterative_correction import SELF_CORRECTIVE_REVISION

_SPECS = {
    1: {"prompt": "No commas.", "instruction_id_list": ["punctuation:no_comma"]},
    2: {"prompt": "Use quotes.", "instruction_id_list": ["startend:quotation"]},
}


def _record(case_id: int) -> str:
    return json.dumps(
        {
            "schema": SCHEMA,
            "case_id": case_id,
            "attempt": 1,
            "valid": True,
            "answer": f"Answer {case_id}",
            "finish_reason": "stop",
            "instruction_id_list": _SPECS[case_id]["instruction_id_list"],
            "descriptions": ["Fixture instruction"],
            "strict": [True],
            "loose": [True],
            "violations": [],
        }
    )


def test_swapped_known_case_records_cannot_publish_a_score() -> None:
    """A real record is still invalid when it belongs to the other selected row."""

    rows = json.dumps([_record(2), _record(1)])

    with pytest.raises(AggregateError):
        aggregate(rows, _SPECS, "ifeval")


@pytest.mark.parametrize(
    ("reducer", "extra"),
    [(aggregate, ()), (aggregate_corrective, (SELF_CORRECTIVE_REVISION,))],
)
def test_zero_case_ifeval_payloads_fail_loudly(reducer, extra) -> None:
    """An empty Evaluation is an execution failure, never a plausible zero score."""

    with pytest.raises(AggregateError, match="no IFEval rows"):
        reducer("[]", _SPECS, "ifeval", *extra)


def test_truthy_text_cannot_impersonate_verifier_booleans() -> None:
    forged = json.loads(_record(1))
    forged["strict"] = ["false"]
    rows = json.dumps([json.dumps(forged), _record(2)])

    with pytest.raises(AggregateError):
        aggregate(rows, _SPECS, "ifeval")
