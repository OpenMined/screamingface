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


def test_a_partial_recordless_case_is_loud_and_retains_the_inner_error() -> None:
    # INVARIANT: an operationally failed Case is not a legitimate incorrect answer and
    # must never be folded into a plausible Benchmark score.
    payload = _rows(
        json.dumps(_record(1, [True, True], [True, True])),
        {
            "error": {
                "kind": "ResolutionError",
                "message": "aigateway returned neither answer content nor tool calls",
            }
        },
    )

    with pytest.raises(AggregateError) as caught:
        aggregate(payload, _SPECS, "ifeval")

    message = str(caught.value)
    assert "case 2" in message
    assert "ResolutionError" in message
    assert "neither answer content nor tool calls" in message


def test_a_recordless_case_without_error_detail_still_names_its_position() -> None:
    payload = _rows(
        "broken row",
        json.dumps(_record(2, [True], [True])),
    )

    with pytest.raises(AggregateError) as caught:
        aggregate(payload, _SPECS, "ifeval")

    assert "case 1" in str(caught.value)


def test_every_row_recordless_raises_instead_of_reporting_zero() -> None:
    # Scoring this would hand the client a plausible 0.0 from a misconfigured assets
    # path — draco's load_rubrics lesson.
    with pytest.raises(AggregateError) as caught:
        aggregate(_rows("broken", "also broken"), _SPECS, "ifeval")

    assert "cases 1, 2" in str(caught.value)


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

    with pytest.raises(AggregateError) as caught:
        aggregate(payload, _SPECS, "ifeval")

    # The stray record cannot smuggle a score into a Case its check never ran for, and
    # the missing authentic grade cannot be recast as an incorrect answer.
    assert "case 2" in str(caught.value)


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
