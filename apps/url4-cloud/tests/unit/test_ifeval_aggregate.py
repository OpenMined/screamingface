"""The IFEval cross-row reducer — check records in, `CandidateResult` out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4_cloud.benchmarks.ifeval.aggregate import (
    SCHEMA,
    AggregateError,
    aggregate,
    load_specs,
)

_SPECS = {
    1: {
        "key": 1000,
        "prompt": "No commas; at least five words.",
        "instruction_id_list": [
            "punctuation:no_comma",
            "length_constraints:number_words",
        ],
        "kwargs": [{}, {"relation": "at least", "num_words": 5}],
    },
    2: {
        "key": 1001,
        "prompt": "Wrap the answer in quotes.",
        "instruction_id_list": ["startend:quotation"],
        "kwargs": [{}],
    },
}


def _record(case_id: int, strict: list[bool], loose: list[bool]) -> dict[str, object]:
    spec = _SPECS[case_id]
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "valid": True,
        "instruction_id_list": spec["instruction_id_list"],
        "strict": strict,
        "loose": loose,
    }


def _rows(*rows: object) -> str:
    return json.dumps(list(rows))


def test_paper_metrics_are_computed_across_cases_and_instructions() -> None:
    # case 1: one of two instructions followed → prompt-level fail, inst-level 1/2.
    # case 2: followed → prompt-level pass, inst-level 1/1.
    payload = _rows(
        json.dumps(_record(1, [True, False], [True, True])),
        json.dumps(_record(2, [True], [True])),
    )

    result = aggregate(payload, _SPECS, "ifeval")

    # INVARIANT: `score` IS the paper's headline metric, prompt-level strict accuracy —
    # the leaderboard number must mean what arXiv:2311.07911 says it means.
    assert result["schema"] == "screamingface.candidate-result.v1"
    assert result["benchmark_id"] == "ifeval"
    assert result["score"] == 0.5
    assert result["metrics"]["inst_level_strict_accuracy"] == round(2 / 3, 4)
    assert result["metrics"]["prompt_level_loose_accuracy"] == 1.0
    assert result["metrics"]["inst_level_loose_accuracy"] == 1.0
    assert result["case_count"] == 2
    assert result["failures"] == []


def test_records_survive_prose_wrapping_and_json_escaping() -> None:
    # WHY: each url4 nesting level prose-wraps and JSON-escapes the level below — the
    # reducer reads only schema-marked spans, never the scaffolding.
    wrapped = "case output → " + json.dumps(_record(1, [True, True], [True, True]))
    escaped = json.dumps({"row": json.dumps(_record(2, [True], [True]))})

    result = aggregate(_rows(wrapped, escaped), _SPECS, "ifeval")

    assert result["score"] == 1.0
    assert result["case_count"] == 2


def test_a_recordless_row_scores_fail_all_and_is_never_a_failure() -> None:
    # INVARIANT: `failures` is ALWAYS empty and `case_count` exact — the SDK hard-rejects
    # anything else (results.py contract). A row whose check crashed scores as
    # fail-all-instructions; deliberate divergence from draco's unscored-never-zero,
    # because a deterministic checker crash is a harness BUG, not judge flake (OME-719).
    payload = _rows(
        json.dumps(_record(1, [True, True], [True, True])),
        "an error object with no check record",
    )

    result = aggregate(payload, _SPECS, "ifeval")

    assert result["case_count"] == 2
    assert result["failures"] == []
    assert result["score"] == 0.5
    assert result["metrics"]["cases_fallback"] == 1


def test_fallback_uses_row_position_for_the_case_identity() -> None:
    payload = _rows(
        "broken row",
        json.dumps(_record(2, [True], [True])),
    )

    result = aggregate(payload, _SPECS, "ifeval")

    fallback = result["case_results"][0]
    assert fallback["case_id"] == 1
    assert fallback["strict"] == [False, False]


def test_every_row_recordless_raises_instead_of_reporting_zero() -> None:
    # INVARIANT: an all-crash run must be LOUD. Scoring it would hand the client a
    # plausible 0.0 from a misconfigured assets path — draco's load_rubrics lesson.
    with pytest.raises(AggregateError):
        aggregate(_rows("broken", "also broken"), _SPECS, "ifeval")


def test_all_crash_error_reports_the_collected_inner_failure() -> None:
    failed = {
        "error": {
            "kind": "ResolutionError",
            "message": "malformed aigateway response",
        }
    }

    with pytest.raises(AggregateError, match="malformed aigateway response"):
        aggregate(_rows(failed), {1: _SPECS[1]}, "ifeval")


def test_metrics_are_flat_numbers_only() -> None:
    payload = _rows(json.dumps(_record(2, [True], [True])))

    result = aggregate(payload, {2: _SPECS[2]}, "ifeval")

    assert all(isinstance(value, (int, float)) for value in result["metrics"].values())


def test_a_record_for_an_unknown_case_id_is_ignored() -> None:
    stray = dict(_record(2, [True], [True]), case_id=99)
    payload = _rows(json.dumps(_record(1, [True, True], [True, True])), json.dumps(stray))

    result = aggregate(payload, _SPECS, "ifeval")

    # Row 2 falls back to positional identity (case 2) with fail-all — the stray record
    # cannot smuggle a score into a case its check never ran for.
    assert result["case_results"][1]["case_id"] == 2
    assert result["case_results"][1]["strict"] == [False]


def test_non_array_payload_raises() -> None:
    with pytest.raises(AggregateError):
        aggregate('{"not": "an array"}', _SPECS, "ifeval")
    with pytest.raises(AggregateError):
        aggregate("not json at all", _SPECS, "ifeval")


def test_load_specs_raises_on_a_missing_or_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(AggregateError):
        load_specs(tmp_path / "missing")


def test_load_specs_reads_case_keyed_files(tmp_path: Path) -> None:
    directory = tmp_path / "instructions"
    directory.mkdir()
    (directory / "1.json").write_text(json.dumps(_SPECS[1]), encoding="utf-8")

    specs = load_specs(directory)

    assert specs[1]["instruction_id_list"] == _SPECS[1]["instruction_id_list"]
