"""HealthBench reducer — every unscorable Case is visible and poisons the exam score.

INVARIANT under test (review finding B1, made worse here by negative points): a
missing rubric asset or failed row must yield a FAILED case result that reaches the
output AND force ``score: None`` — a silently dropped Case would inflate the mean by
removing exactly the rows the subset exists to keep.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4_cloud.benchmarks.healthbench.aggregate import (
    AggregateError,
    CandidateResult,
    aggregate,
    load_rubric_points,
)
from url4_cloud.benchmarks.healthbench.case_evaluation import (
    CASE_EVALUATION_SCHEMA,
    RUBRIC_EVALUATION_SCHEMA,
)
from url4_cloud.benchmarks.healthbench.verdict import SCHEMA as VERDICT_SCHEMA


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


def _evidence(case_id: int, rubric_id: int, met: bool) -> dict[str, object]:
    return {
        "schema": VERDICT_SCHEMA,
        "case_id": case_id,
        "rubric_id": rubric_id,
        "producer_type": "model",
        "producer_id": "judge",
        "valid": True,
        "criteria_met": met,
        "explanation": "…",
        "raw_output": "{}",
    }


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
                "evidence": _evidence(case_id, rubric_id, met),
            }
            for rubric_id, met in verdicts.items()
        ],
    }


def _failure_codes(result: CandidateResult) -> dict[int, str | None]:
    """case_id → the Case's single failure code (None when scored clean)."""

    return {
        case["case_id"]: (case["failures"][0]["code"] if case["failures"] else None)
        for case in result["cases"]
    }


def test_fully_judged_cases_score_and_mean_unclipped(tmp_path: Path) -> None:
    _write_rubric(tmp_path, 1, [7, 8, -6])
    _write_rubric(tmp_path, 2, [5])
    rows = json.dumps(
        [
            _case_row(1, {1: False, 2: False, 3: True}),  # (0-6)/15 = -0.4
            _case_row(2, {1: True}),  # 1.0
        ]
    )
    result = aggregate(rows, tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1, 2))
    assert result["score"] == pytest.approx((1.0 - 0.4) / 2)
    assert result["metrics"].get("scored_cases") == 2
    assert result["metrics"].get("failed_cases") == 0
    assert result["metrics"].get("verdict_coverage") == 1.0
    assert _failure_codes(result) == {1: None, 2: None}
    # SDK Case Result contract (seen live in the smoke run): every Case carries
    # the full key set, a scored Case carries a rubric grade, and evidence rows
    # sit under grade.checks — not in any home-grown envelope.
    first = result["cases"][0]
    assert set(first) == {
        "case_id",
        "input",
        "output",
        "finish_reason",
        "grade",
        "failures",
        "metadata",
    }
    assert first["output"] == "output-1"
    grade = first["grade"]
    assert grade is not None
    assert grade["method"] == "rubric"
    assert grade["score"] == pytest.approx(-0.4)
    assert [check["id"] for check in grade["checks"]] == ["1", "2", "3"]
    assert grade["checks"][2]["evidence"][0]["outcome"] == "MET"
    # The SDK's candidate-result contract requires a top-level failures list even
    # when empty — omitting the key breaks report decoding (seen live in the smoke
    # run); healthbench routes every failure to a Case, so it is always [].
    assert result["failures"] == []
    # Same decoder rejects non-numeric metric values (also seen live) — the
    # scoring label must never reappear inside metrics.
    assert all(isinstance(value, (int, float)) for value in result["metrics"].values())


def test_a_missing_rubric_asset_fails_the_case_and_the_exam(tmp_path: Path) -> None:
    _write_rubric(tmp_path, 1, [7])
    rows = json.dumps([_case_row(1, {1: True}), _case_row(2, {1: True})])
    result = aggregate(rows, tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1, 2))
    # B1: the broken Case is IN the output, and the exam refuses to publish a mean.
    assert result["score"] is None
    assert _failure_codes(result) == {1: None, 2: "missing_rubric_asset"}
    # SDK report rule: an unscored Candidate must carry EMPTY metrics — the
    # per-Case failures rows are the diagnosis channel instead.
    assert result["metrics"] == {}


def test_an_error_collected_row_fails_its_case(tmp_path: Path) -> None:
    _write_rubric(tmp_path, 1, [7])
    _write_rubric(tmp_path, 2, [3])
    rows = json.dumps(
        [
            _case_row(1, {1: True}),
            {"schema": CASE_EVALUATION_SCHEMA, "case_id": 2, "error": "candidate died"},
        ]
    )
    result = aggregate(rows, tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1, 2))
    assert result["score"] is None
    assert _failure_codes(result)[2] == "case_error"
    failed = next(case for case in result["cases"] if case["case_id"] == 2)
    assert failed["grade"] is None


def test_partial_verdicts_never_score(tmp_path: Path) -> None:
    # INVARIANT: a judge failure on a penalty item would erase the penalty — a Case
    # missing any verdict must fail, never score from the items that did parse.
    _write_rubric(tmp_path, 1, [7, -6])
    rows = json.dumps([_case_row(1, {1: True})])  # the -6 item was never judged
    result = aggregate(rows, tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1,))
    assert result["score"] is None
    assert _failure_codes(result) == {1: "incomplete_verdicts"}
    # The judged item's evidence is still auditable via grade.checks even though
    # the Case failed — grade.score stays None (the contract's "no score" form).
    grade = result["cases"][0]["grade"]
    assert grade is not None
    assert grade["score"] is None
    assert len(grade["checks"]) == 1
    assert result["metrics"] == {}  # unscored → empty (SDK report rule)


def test_invalid_judge_evidence_counts_and_fails_the_case(tmp_path: Path) -> None:
    _write_rubric(tmp_path, 1, [7])
    row = _case_row(1, {1: True})
    evaluations = row["rubric_evaluations"]
    assert isinstance(evaluations, list)
    evaluations[0]["evidence"] = {
        "schema": VERDICT_SCHEMA,
        "case_id": 1,
        "rubric_id": 1,
        "valid": False,
        "reason": "invalid_json",
        "raw_output": "not json",
    }
    result = aggregate(
        json.dumps([row]), tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1,)
    )
    assert result["score"] is None
    assert result["metrics"] == {}  # unscored → empty (SDK report rule)
    assert _failure_codes(result) == {1: "incomplete_verdicts"}


def test_a_missing_case_row_is_visible(tmp_path: Path) -> None:
    _write_rubric(tmp_path, 1, [7])
    _write_rubric(tmp_path, 2, [3])
    result = aggregate(
        json.dumps([_case_row(1, {1: True})]),
        tmp_path,
        benchmark_id="hb",
        benchmark_revision="rev",
        case_ids=(1, 2),
    )
    assert result["score"] is None
    assert _failure_codes(result)[2] == "missing_case_row"


def test_unusable_row_payloads_raise_before_scoring(tmp_path: Path) -> None:
    with pytest.raises(AggregateError):
        aggregate("not json", tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1,))
    with pytest.raises(AggregateError):
        aggregate("[]", tmp_path, benchmark_id="hb", benchmark_revision="rev", case_ids=(1,))


def test_load_rubric_points_rejects_malformed_assets(tmp_path: Path) -> None:
    assert load_rubric_points(tmp_path, 9) is None  # absent
    rubric_dir = tmp_path / "rubrics"
    rubric_dir.mkdir()
    (rubric_dir / "9.json").write_text("not json", encoding="utf-8")
    assert load_rubric_points(tmp_path, 9) is None
    (rubric_dir / "9.json").write_text(
        json.dumps({"items": [{"rubric_id": 1, "points": 7.5}]}), encoding="utf-8"
    )
    assert load_rubric_points(tmp_path, 9) is None  # float points are corrupt
    (rubric_dir / "9.json").write_text(
        json.dumps({"items": [{"rubric_id": 2, "points": 7}]}), encoding="utf-8"
    )
    assert load_rubric_points(tmp_path, 9) is None  # ids must be consecutive from 1
