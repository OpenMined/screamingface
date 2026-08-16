"""Cross-Benchmark conformance for shared terminal Candidate outcomes."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from url4_cloud.benchmarks.case_execution import case_execution_payload
from url4_cloud.benchmarks.contract import encode_candidate_invocation
from url4_cloud.benchmarks.draco.aggregate import aggregate as aggregate_draco
from url4_cloud.benchmarks.healthbench.aggregate import aggregate as aggregate_healthbench
from url4_cloud.benchmarks.ifeval.aggregate import aggregate as aggregate_ifeval

AggregateFixture = Callable[[Path, dict[str, object]], dict[str, Any]]


def _ifeval(_root: Path, row: dict[str, object]) -> dict[str, Any]:
    spec = {
        1: {
            "prompt": "Return exactly one word.",
            "instruction_id_list": ["length_constraints:number_words"],
            "kwargs": [{"relation": "at most", "num_words": 1}],
        }
    }
    return aggregate_ifeval(json.dumps([row]), spec, "ifeval", [1], selected_case_count=1)


def _draco(_root: Path, row: dict[str, object]) -> dict[str, Any]:
    return aggregate_draco(
        json.dumps([row]),
        rubrics={},
        benchmark_id="draco",
        selected_cases=[{"id": 1, "input": "Question"}],
    )


def _healthbench(root: Path, row: dict[str, object]) -> dict[str, Any]:
    (root / "cases.json").write_text(
        json.dumps([{"id": 1, "input": "Patient question"}]),
        encoding="utf-8",
    )
    return aggregate_healthbench(
        json.dumps([row]),
        root,
        benchmark_id="healthbench-worst30",
        benchmark_revision="fixture",
        case_ids=(1,),
    )


@pytest.mark.parametrize("aggregate", (_ifeval, _draco, _healthbench))
@pytest.mark.parametrize("refusal", ("I cannot answer that.", None))
def test_refusal_survives_a_later_grading_failure_across_benchmarks(
    tmp_path: Path,
    aggregate: AggregateFixture,
    refusal: str | None,
) -> None:
    invocation = encode_candidate_invocation(
        "",
        "content_filter",
        refusal,
        status="refused",
    )
    row = case_execution_payload(
        1,
        invocation,
        [
            {
                "error": {
                    "kind": "ResolutionError",
                    "code": "judge_unavailable",
                    "message": "Judge unavailable after retries",
                    "permanent": False,
                }
            }
        ],
    )

    result = aggregate(tmp_path, row)

    assert result["score"] is None
    assert result["coverage"] == 0.0
    assert result["metrics"] == {}
    case = result["cases"][0]
    assert case["status"] == "refused"
    assert case["output"] is None
    assert case["refusal"] == refusal
    assert case["grade"]["score"] is None
    assert case["failures"][0]["stage"] == "grading"
    assert case["failures"][0]["code"] == "judge_unavailable"


@pytest.mark.parametrize("aggregate", (_ifeval, _draco, _healthbench))
def test_case_execution_identity_mismatch_fails_loudly_across_benchmarks(
    tmp_path: Path,
    aggregate: AggregateFixture,
) -> None:
    invocation = encode_candidate_invocation(
        "answer",
        "stop",
        None,
        status="completed",
    )
    row = case_execution_payload(
        2,
        invocation,
        [
            {
                "error": {
                    "kind": "ResolutionError",
                    "code": "judge_unavailable",
                    "message": "Judge unavailable after retries",
                    "permanent": False,
                }
            }
        ],
    )

    with pytest.raises(ValueError, match="claims case_id"):
        aggregate(tmp_path, row)
