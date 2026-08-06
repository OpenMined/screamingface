"""HealthBench results must decode with the REAL SDK decoder — no fixture copies.

WHY this test exists: the candidate-result contract lives in the SDK
(``screamingface._evaluation.results`` + ``screamingface.report``), and the engine
side has no compile-time link to it. Before this guard, four contract mismatches
(missing ``failures``, non-numeric metric, home-grown Case shape, metrics on an
unscored Candidate) each survived the unit suite and failed only in a live paid
smoke run. Feeding ``aggregate()`` output through the SDK's own decode functions
makes the next drift fail HERE, for free.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from screamingface._evaluation.results import _cases as sdk_decode_cases
from screamingface._evaluation.results import _failures as sdk_decode_failures
from screamingface._evaluation.results import _metrics as sdk_decode_metrics

from url4_cloud.benchmarks.healthbench.aggregate import aggregate
from url4_cloud.benchmarks.healthbench.case_evaluation import (
    CASE_EVALUATION_SCHEMA,
    RUBRIC_EVALUATION_SCHEMA,
)
from url4_cloud.benchmarks.healthbench.verdict import SCHEMA as VERDICT_SCHEMA

# The SDK's required top-level key set (results.py `_keys` on "Candidate result").
_CANDIDATE_RESULT_KEYS = {
    "schema",
    "benchmark_id",
    "benchmark_revision",
    "case_count",
    "score",
    "metrics",
    "cases",
    "failures",
}


def _write_rubric(root: Path, case_id: int, points: list[int]) -> None:
    rubric_dir = root / "rubrics"
    rubric_dir.mkdir(parents=True, exist_ok=True)
    (rubric_dir / f"{case_id}.json").write_text(
        json.dumps(
            {
                "hf_id": f"hf-{case_id}",
                "items": [
                    {"rubric_id": index, "criterion": f"c{index}", "points": value}
                    for index, value in enumerate(points, start=1)
                ],
            }
        ),
        encoding="utf-8",
    )


def _case_row(case_id: int, verdicts: dict[int, bool]) -> dict[str, object]:
    return {
        "schema": CASE_EVALUATION_SCHEMA,
        "case_id": case_id,
        "case": {
            "case_id": case_id,
            "input": f"input-{case_id}",
            "output": f"output-{case_id}",
            "finish_reason": "stop",
            "metadata": {},
        },
        "rubric_evaluations": [
            {
                "schema": RUBRIC_EVALUATION_SCHEMA,
                "case_id": case_id,
                "rubric_id": rubric_id,
                "rubric": {"rubric_id": rubric_id, "rubric_item": f"[1] c{rubric_id}"},
                "evidence": {
                    "schema": VERDICT_SCHEMA,
                    "case_id": case_id,
                    "rubric_id": rubric_id,
                    "producer_type": "model",
                    "producer_id": "judge",
                    "valid": True,
                    "criteria_met": met,
                    "explanation": "…",
                    "raw_output": "{}",
                },
            }
            for rubric_id, met in verdicts.items()
        ],
    }


def _sdk_decode(result: dict) -> None:
    """Run every SDK decode stage that has bitten a live run; raises on drift."""

    assert set(result) == _CANDIDATE_RESULT_KEYS
    sdk_decode_cases(result["cases"])
    sdk_decode_failures(result["failures"], "Candidate failures")
    metrics = sdk_decode_metrics(result["metrics"])
    # report.Candidate rule: a failed or unscored Candidate cannot contain metrics.
    if result["score"] is None:
        assert not metrics, "unscored Candidate must carry empty metrics (SDK report rule)"


def test_scored_result_decodes_with_the_sdk(tmp_path: Path) -> None:
    _write_rubric(tmp_path, 1, [7, -6])
    rows = json.dumps([_case_row(1, {1: True, 2: False})])
    result = aggregate(rows, tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1,))
    assert result["score"] == pytest.approx(1.0)
    _sdk_decode(result)


def test_every_failure_rung_decodes_with_the_sdk(tmp_path: Path) -> None:
    # One aggregate exercising all ladder rungs at once: missing rubric asset (3),
    # missing row (4), error row (2), incomplete verdicts (1 judged of 2).
    _write_rubric(tmp_path, 1, [7, -6])
    _write_rubric(tmp_path, 2, [5])
    _write_rubric(tmp_path, 4, [5])
    rows = json.dumps(
        [
            _case_row(1, {1: True}),
            {"schema": CASE_EVALUATION_SCHEMA, "case_id": 2, "error": "candidate died"},
        ]
    )
    result = aggregate(
        rows, tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1, 2, 3, 4)
    )
    assert result["score"] is None
    _sdk_decode(result)
