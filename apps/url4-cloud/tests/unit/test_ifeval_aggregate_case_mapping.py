"""Canonical IFEval rows must carry the verifier record for their selected Case."""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.ifeval.aggregate import (
    SCHEMA,
    AggregateError,
)
from url4_cloud.benchmarks.ifeval.aggregate import (
    aggregate as _aggregate,
)
from url4_cloud.benchmarks.ifeval.aggregate import (
    aggregate_corrective as _aggregate_corrective,
)
from url4_cloud.benchmarks.ifeval.case_evaluation import bind_case_evaluation
from url4_cloud.benchmarks.ifeval.iterative_correction import SELF_CORRECTIVE_REVISION

_SPECS = {
    1: {"prompt": "No commas.", "instruction_id_list": ["punctuation:no_comma"]},
    2: {"prompt": "Use quotes.", "instruction_id_list": ["startend:quotation"]},
}


def _selected_cases(specs=_SPECS):
    return [{"id": case_id, "input": spec["prompt"]} for case_id, spec in specs.items()]


def aggregate(payload, specs, benchmark_id):
    return _aggregate(payload, specs, benchmark_id, selected_cases=_selected_cases(specs))


def aggregate_corrective(payload, specs, benchmark_id, benchmark_revision):
    return _aggregate_corrective(
        payload,
        specs,
        benchmark_id,
        benchmark_revision,
        selected_cases=_selected_cases(specs),
    )


def _record(case_id: int) -> dict[str, object]:
    return {
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


def _evaluation(case_id: int) -> dict[str, object]:
    return bind_case_evaluation(case_id, [_record(case_id)])


def test_swapped_known_case_records_cannot_publish_a_score() -> None:
    """A real record is still invalid when it belongs to the other selected row."""

    rows = json.dumps([_evaluation(2), _evaluation(1)])

    result = aggregate(rows, _SPECS, "ifeval")

    assert result["score"] is None
    assert [case["grade"] for case in result["cases"]] == [None, None]


@pytest.mark.parametrize(
    ("reducer", "extra"),
    [(aggregate, ()), (aggregate_corrective, (SELF_CORRECTIVE_REVISION,))],
)
def test_zero_case_ifeval_payloads_fail_loudly(reducer, extra) -> None:
    """An empty Evaluation is an execution failure, never a plausible zero score."""

    with pytest.raises(AggregateError, match="no IFEval rows"):
        reducer("[]", _SPECS, "ifeval", *extra)


def test_truthy_text_cannot_impersonate_verifier_booleans() -> None:
    forged = _record(1)
    forged["strict"] = ["false"]
    rows = json.dumps(
        [
            bind_case_evaluation(1, [forged]),
            _evaluation(2),
        ]
    )

    result = aggregate(rows, _SPECS, "ifeval")

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None


def test_nonsequential_official_case_ids_follow_the_public_case_sequence() -> None:
    specs = {
        1000: {"prompt": "First", "instruction_id_list": ["punctuation:no_comma"]},
        102: {"prompt": "Second", "instruction_id_list": ["startend:quotation"]},
    }
    selected_cases = [{"id": 1000, "input": "First"}, {"id": 102, "input": "Second"}]

    def record(case_id: int, instruction_id: str) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "case_id": case_id,
            "attempt": 1,
            "valid": True,
            "answer": "Answer",
            "finish_reason": "stop",
            "instruction_id_list": [instruction_id],
            "descriptions": ["Fixture instruction"],
            "strict": [True],
            "loose": [True],
            "violations": [],
        }

    rows = json.dumps(
        [
            bind_case_evaluation(1000, [record(1000, "punctuation:no_comma")]),
            bind_case_evaluation(102, [record(102, "startend:quotation")]),
        ]
    )

    result = _aggregate(rows, specs, "ifeval", selected_cases=selected_cases)

    assert result["score"] == 1.0
    assert [case["case_id"] for case in result["cases"]] == [1000, 102]
