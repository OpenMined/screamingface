"""The IFEval cross-row reducer — check records in, `CandidateResult` out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4_cloud.benchmarks.ifeval.aggregate import (
    SCHEMA,
    AggregateError,
    aggregate,
    aggregate_corrective,
    load_specs,
)
from url4_cloud.benchmarks.ifeval.case_evaluation import (
    CASE_EVALUATION_SCHEMA,
    bind_case_evaluation,
)
from url4_cloud.benchmarks.ifeval.definition import REVISION as IFEVAL_REVISION
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
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

# The installed selection order (cases.json file order) — row N is graded against
# _ORDER[N], never against sorted spec ids.
_ORDER = [1, 2]


def _record(case_id: int, strict: list[bool], loose: list[bool]) -> dict[str, object]:
    spec = _SPECS[case_id]
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "attempt": 1,
        "valid": True,
        "answer": f"Answer {case_id}",
        "finish_reason": "stop",
        "instruction_id_list": spec["instruction_id_list"],
        "descriptions": [
            f"Instruction {index}" for index in range(1, len(spec["instruction_id_list"]) + 1)
        ],
        "strict": strict,
        "loose": loose,
        "violations": [],
    }


def _rows(*rows: object) -> str:
    return json.dumps(list(rows))


def _evaluation(case_id: int, strict: list[bool], loose: list[bool]) -> dict[str, object]:
    return bind_case_evaluation(case_id, [_record(case_id, strict, loose)])


def test_paper_metrics_are_computed_across_cases_and_instructions() -> None:
    # case 1: one of two instructions followed → prompt-level fail, inst-level 1/2.
    # case 2: followed → prompt-level pass, inst-level 1/1.
    payload = _rows(
        _evaluation(1, [True, False], [True, True]),
        _evaluation(2, [True], [True]),
    )

    result = aggregate(payload, _SPECS, "ifeval", _ORDER)

    # INVARIANT: `score` IS the paper's headline metric, prompt-level strict accuracy —
    # the leaderboard number must mean what arXiv:2311.07911 says it means.
    assert result["schema"] == "screamingface.candidate-result.v1"
    assert result["benchmark_id"] == "ifeval"
    assert result["benchmark_revision"] == IFEVAL_REVISION
    assert result["score"] == 0.5
    assert result["metrics"]["inst_level_strict_accuracy"] == round(2 / 3, 4)
    assert result["metrics"]["prompt_level_loose_accuracy"] == 1.0
    assert result["metrics"]["inst_level_loose_accuracy"] == 1.0
    # Canonical report contract: pass_rate mirrors inst-level strict accuracy and
    # coverage is (checked - fallback) / selected — all 2 cases were checked here.
    assert result["metrics"]["pass_rate"] == round(2 / 3, 4)
    assert result["metrics"]["coverage"] == 1.0
    assert result["case_count"] == 2
    assert result["cases"][0]["input"] == _SPECS[1]["prompt"]
    assert result["cases"][0]["output"] == "Answer 1"
    assert result["cases"][0]["grade"]["checks"][0]["evidence"][0]["outcome"] == "PASS"
    # INVARIANT: each check carries its own MET/UNMET verdict (strict verifier decides) —
    # readers of the report schema judge a check by its outcome, not by digging into
    # evidence, and a check without one renders as unjudged.
    assert result["cases"][0]["grade"]["checks"][0]["outcome"] == "MET"
    assert result["cases"][0]["grade"]["checks"][1]["outcome"] == "UNMET"
    assert result["failures"] == []


def test_exact_case_evaluations_survive_the_collect_boundary() -> None:
    result = aggregate(
        _rows(
            _evaluation(1, [True, True], [True, True]),
            _evaluation(2, [True], [True]),
        ),
        _SPECS,
        "ifeval",
        _ORDER,
    )

    assert result["score"] == 1.0
    assert result["case_count"] == 2


def test_a_partial_failed_case_is_retained_without_a_partial_score() -> None:
    # INVARIANT: an operationally failed Case is not a legitimate incorrect answer and
    # must never be folded into a plausible Benchmark score.
    payload = _rows(
        _evaluation(1, [True, True], [True, True]),
        {
            "error": {
                "kind": "ResolutionError",
                "message": "aigateway returned neither answer content nor tool calls",
            }
        },
    )

    result = aggregate(payload, _SPECS, "ifeval", _ORDER)

    assert result["score"] is None
    assert result["cases"][0]["grade"]["score"] == 1.0
    assert result["cases"][1]["grade"] is None
    assert result["cases"][1]["failures"][0]["message"] == (
        "aigateway returned neither answer content nor tool calls"
    )


def test_an_invalid_case_evaluation_is_retained_as_a_grading_failure() -> None:
    payload = _rows(
        "broken row",
        _evaluation(2, [True], [True]),
    )

    result = aggregate(payload, _SPECS, "ifeval", _ORDER)

    assert result["score"] is None
    assert result["cases"][0]["failures"][0]["code"] == "invalid_case_evaluation"


def test_every_failed_case_returns_null_instead_of_reporting_zero() -> None:
    # Scoring this would hand the client a plausible 0.0 from a misconfigured assets
    # path — draco's load_rubrics lesson.
    result = aggregate(_rows("broken", "also broken"), _SPECS, "ifeval", _ORDER)

    assert result["score"] is None
    assert [case["grade"] for case in result["cases"]] == [None, None]


def test_all_crash_result_retains_the_collected_inner_failure() -> None:
    failed = {
        "error": {
            "kind": "ResolutionError",
            "message": "malformed aigateway response",
        }
    }

    result = aggregate(_rows(failed), {1: _SPECS[1]}, "ifeval", [1])

    assert result["score"] is None
    assert result["cases"][0]["failures"][0]["message"] == "malformed aigateway response"


def test_metrics_are_flat_numbers_only() -> None:
    payload = _rows(_evaluation(2, [True], [True]))

    result = aggregate(payload, {2: _SPECS[2]}, "ifeval", [2])

    assert all(isinstance(value, (int, float)) for value in result["metrics"].values())


def test_canonical_contract_metrics_are_published_for_every_scored_aggregate() -> None:
    """INVARIANT: every scored aggregate publishes the canonical trio (score,
    pass_rate, coverage) in [0, 1] — the SDK report tiles and its low-coverage
    warning read exactly these keys across all benchmarks (draco is the reference).
    """

    payload = _rows(
        _evaluation(1, [True, False], [True, True]),
        _evaluation(2, [True], [True]),
    )
    single_pass = aggregate(payload, _SPECS, "ifeval", _ORDER)
    corrective = aggregate_corrective(
        payload, _SPECS, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, _ORDER
    )

    for result in (single_pass, corrective):
        assert 0.0 <= result["score"] <= 1.0
        assert 0.0 <= result["metrics"]["pass_rate"] <= 1.0
        assert 0.0 <= result["metrics"]["coverage"] <= 1.0
        # IFEval's mapping: pass_rate IS instruction-level strict accuracy.
        assert result["metrics"]["pass_rate"] == result["metrics"]["inst_level_strict_accuracy"]
        assert result["metrics"]["coverage"] == 1.0


def test_a_record_for_an_unknown_case_id_is_ignored() -> None:
    stray = dict(_record(2, [True], [True]), case_id=99)
    stray_evaluation = {
        "schema": CASE_EVALUATION_SCHEMA,
        "case_id": 2,
        "attempts": [stray],
    }
    payload = _rows(_evaluation(1, [True, True], [True, True]), stray_evaluation)

    result = aggregate(payload, _SPECS, "ifeval", _ORDER)

    # The stray record cannot smuggle a score into a Case its check never ran for, and
    # the missing authentic grade cannot be recast as an incorrect answer.
    assert result["score"] is None
    assert result["cases"][1]["grade"] is None


def test_non_array_payload_raises() -> None:
    with pytest.raises(AggregateError):
        aggregate('{"not": "an array"}', _SPECS, "ifeval", _ORDER)
    with pytest.raises(AggregateError):
        aggregate("not json at all", _SPECS, "ifeval", _ORDER)


def test_load_specs_raises_on_a_missing_or_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(AggregateError):
        load_specs(tmp_path / "missing")


def test_load_specs_reads_case_keyed_files(tmp_path: Path) -> None:
    directory = tmp_path / "instructions"
    directory.mkdir()
    (directory / "1.json").write_text(json.dumps(_SPECS[1]), encoding="utf-8")

    specs = load_specs(directory)

    assert specs[1]["instruction_id_list"] == _SPECS[1]["instruction_id_list"]
