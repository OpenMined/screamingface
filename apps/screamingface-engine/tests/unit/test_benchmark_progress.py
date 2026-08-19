"""Benchmark-native progress stays generic while each aggregate owns its score math."""

from __future__ import annotations

import json
from typing import Any

import pytest

from screamingface_engine.benchmarks.contract import CandidateResult
from screamingface_engine.benchmarks.progress import (
    PROGRESS_LOG_KIND,
    BenchmarkProgressAdapter,
    BenchmarkProgressSignal,
    benchmark_progress_session,
    final_aggregate,
    progress_endpoint,
)
from screamingface_engine.runner.executor import _RunState
from url4.peer.server import Request
from url4.streaming.protocol import LogData


def _aggregate(rows_json: str, selected_case_count: int) -> dict[str, Any]:
    rows = json.loads(rows_json)
    cases: list[dict[str, object]] = []
    scores: list[float] = []
    for case_id, row in enumerate(rows, start=1):
        if isinstance(row, dict) and isinstance(row.get("score"), int | float):
            score = float(row["score"])
            scores.append(score)
            cases.append(
                {
                    "status": "scored",
                    "case_id": case_id,
                    "input": f"input-{case_id}",
                    "output": f"output-{case_id}",
                    "finish_reason": "stop",
                    "refusal": None,
                    "grade": {"method": "fixture", "score": score, "metrics": {}, "checks": []},
                    "failures": [],
                    "metadata": {},
                }
            )
        else:
            cases.append(
                {
                    "status": "failed",
                    "case_id": case_id,
                    "input": f"input-{case_id}",
                    "output": None,
                    "finish_reason": None,
                    "refusal": None,
                    "grade": None,
                    "failures": [
                        {
                            "stage": "grading",
                            "code": "pending_case",
                            "message": "not complete",
                            "retryable": None,
                            "case_id": case_id,
                            "metadata": {},
                        }
                    ],
                    "metadata": {},
                }
            )
    result = CandidateResult.model_validate(
        {
            "benchmark_id": "fixture",
            "benchmark_revision": "revision",
            "case_count": selected_case_count,
            "score": (sum(scores) / len(scores) if scores else None),
            "coverage": round(len(scores) / selected_case_count, 4),
            "metrics": ({"native": True} if scores else {}),
            "cases": cases,
            "failures": [],
        }
    )
    return result.as_payload()


def _adapter() -> BenchmarkProgressAdapter:
    return BenchmarkProgressAdapter(
        benchmark_id="fixture",
        benchmark_revision="revision",
        available_case_count=2,
        case_order=lambda: (1, 2),
        aggregate=_aggregate,
    )


@pytest.mark.parametrize("score", (-0.4, 0.0, 0.75))
def test_progress_uses_the_benchmark_aggregate_and_reconciles_the_final_score(
    score: float,
) -> None:
    adapter = _adapter()
    endpoint = progress_endpoint(adapter)
    snapshots: list[BenchmarkProgressSignal] = []

    with benchmark_progress_session(snapshots.append):
        assert (
            endpoint(
                Request(
                    adapter.benchmark_id,
                    json.dumps({"case_id": 1, "value": "input-1"}),
                    "candidate:2",
                    {},
                )
            )
            == "input-1"
        )
        endpoint(
            Request(
                adapter.benchmark_id,
                json.dumps({"case_id": 1, "value": "answer-1"}),
                "grading:2",
                {},
            )
        )
        endpoint(
            Request(
                adapter.benchmark_id,
                json.dumps({"case_id": 1, "value": json.dumps({"score": score})}),
                "complete:2",
                {},
            )
        )
        final = final_aggregate(adapter)(
            json.dumps([{"score": score}, {"score": score}]),
            2,
        )

    stages = [
        (item.queued, item.running_candidate, item.grading, item.complete) for item in snapshots
    ]
    assert stages == [
        (1, 1, 0, 0),
        (1, 0, 1, 0),
        (1, 0, 0, 1),
        (0, 0, 0, 2),
    ]
    assert snapshots[0].provisional_score is None
    assert snapshots[2].provisional_score == score
    assert snapshots[2].coverage == 0.5
    assert snapshots[-1].provisional_score == final["score"] == score
    assert snapshots[-1].coverage == final["coverage"] == 1.0


def test_progress_signal_uses_the_existing_structured_log_wire() -> None:
    signal = BenchmarkProgressSignal(
        benchmark_id="ifeval",
        benchmark_revision="revision",
        total=2,
        queued=1,
        running_candidate=0,
        grading=0,
        complete=1,
        scored=1,
        coverage=0.5,
        provisional_score=1.0,
    )

    frames = _RunState().map(signal)

    assert len(frames) == 1
    payload = frames[0].payload
    assert isinstance(payload, LogData)
    assert payload.attributes["screamingface.event.kind"] == PROGRESS_LOG_KIND
    assert payload.attributes["score.provisional"] == 1.0


def test_invalid_progress_metadata_never_changes_the_pass_through_value() -> None:
    endpoint = progress_endpoint(_adapter())
    snapshots: list[BenchmarkProgressSignal] = []

    with benchmark_progress_session(snapshots.append):
        value = endpoint(
            Request(
                "fixture",
                json.dumps({"case_id": None, "value": "candidate answer"}),
                "grading:2",
                {},
            )
        )

    assert value == "candidate answer"
    assert snapshots == []


def test_progress_sink_failure_never_changes_the_pass_through_value() -> None:
    endpoint = progress_endpoint(_adapter())

    def broken_sink(_signal: BenchmarkProgressSignal) -> None:
        raise RuntimeError("progress queue is full")

    with benchmark_progress_session(broken_sink):
        value = endpoint(
            Request(
                "fixture",
                json.dumps({"case_id": 1, "value": "candidate answer"}),
                "candidate:2",
                {},
            )
        )

    assert value == "candidate answer"


def test_final_reconciliation_does_not_repeat_an_identical_complete_snapshot() -> None:
    adapter = BenchmarkProgressAdapter(
        benchmark_id="fixture",
        benchmark_revision="revision",
        available_case_count=1,
        case_order=lambda: (1,),
        aggregate=_aggregate,
    )
    endpoint = progress_endpoint(adapter)
    snapshots: list[BenchmarkProgressSignal] = []

    with benchmark_progress_session(snapshots.append):
        endpoint(
            Request(
                "fixture",
                json.dumps({"case_id": 1, "value": json.dumps({"score": 0.5})}),
                "complete:1",
                {},
            )
        )
        final_aggregate(adapter)(json.dumps([{"score": 0.5}]), 1)

    assert len(snapshots) == 1
    assert snapshots[0].complete == snapshots[0].scored == 1


def test_progress_rejects_a_stage_partition_that_cannot_describe_the_selection() -> None:
    with pytest.raises(ValueError, match="sum to total"):
        BenchmarkProgressSignal(
            benchmark_id="ifeval",
            benchmark_revision="revision",
            total=2,
            queued=0,
            running_candidate=0,
            grading=0,
            complete=1,
            scored=1,
            coverage=0.5,
            provisional_score=1.0,
        )
