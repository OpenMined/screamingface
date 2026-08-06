"""DRACO aggregation — the paper's exact scoring math.

FEATURE: the cross-row reducer of a Candidate benchmark run turns per-criterion Judge verdicts
into a Candidate Result.
STORY: as a researcher, the score I get back is the DRACO paper's `normalized_score`, not an
approximation, so a leaderboard number means what the paper says it means.

INVARIANT: the formulas here mirror `screamingface-benchmarks/benchmarking/graders/rubric.py`
(arXiv:2602.11685 §4.2) exactly. Every expected value below is hand-computed from the rubric in
`_RUBRIC`, so a drift in either implementation shows up as an arithmetic failure, not a vague
"scores moved" regression.
"""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.draco import aggregate as agg
from url4_cloud.benchmarks.draco import scoring
from url4_cloud.benchmarks.draco.case_evaluation import (
    bind_case_evaluation,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.definition import REVISION as DRACO_REVISION
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA

# Two sections, one negative criterion. Positive weights sum to 4 (a1=2, a2=1, b1=1).
_RUBRIC = {
    "sections": [
        {
            "id": "Factual Accuracy",
            "criteria": [
                {"id": "a1", "weight": 2, "requirement": "cites a source"},
                {"id": "a2", "weight": 1, "requirement": "states the date"},
                {"id": "a3", "weight": -3, "requirement": "invents a statistic"},
            ],
        },
        {"id": "Presentation", "criteria": [{"id": "b1", "weight": 1, "requirement": "is terse"}]},
    ]
}


def _verdicts(**kwargs: bool) -> dict[str, bool]:
    return dict(kwargs)


def _selected_cases(*case_ids: int) -> list[dict[str, object]]:
    return [{"id": case_id, "input": f"Question {case_id}"} for case_id in case_ids]


# --- normalized_score -----------------------------------------------------------


def test_perfect_answer_scores_one() -> None:
    # a1+a2+b1 MET (2+1+1=4), a3 UNMET → 4/4
    v = _verdicts(a1=True, a2=True, a3=False, b1=True)

    assert scoring.normalized_score(_RUBRIC, v) == 1.0


def test_a_met_negative_criterion_subtracts_from_the_numerator() -> None:
    # 2 + 0 + (-3) + 1 = 0 over denom 4 → 0.0
    v = _verdicts(a1=True, a2=False, a3=True, b1=True)

    assert scoring.normalized_score(_RUBRIC, v) == 0.0


def test_the_score_is_clamped_at_zero_not_negative() -> None:
    # 0 + 0 + (-3) + 0 = -3 over 4 → clamped to 0.0, never -0.75
    v = _verdicts(a1=False, a2=False, a3=True, b1=False)

    assert scoring.normalized_score(_RUBRIC, v) == 0.0


def test_partial_credit_is_weight_aware() -> None:
    # a1 only: 2/4
    assert (
        scoring.normalized_score(_RUBRIC, _verdicts(a1=True, a2=False, a3=False, b1=False)) == 0.5
    )


def test_all_negative_rubric_returns_zero_rather_than_dividing_by_zero() -> None:
    """The paper does not define this case; returning 0.0 beats inventing a formula."""
    rubric = {"sections": [{"id": "X", "criteria": [{"id": "n1", "weight": -1}]}]}

    assert scoring.normalized_score(rubric, {"n1": False}) == 0.0


# --- pass_rate ------------------------------------------------------------------


def test_pass_rate_counts_avoided_negatives_as_correct() -> None:
    # a1 MET ✓, a2 MET ✓, a3 UNMET ✓ (anti-pattern avoided), b1 MET ✓ → 4/4
    assert scoring.pass_rate(_RUBRIC, _verdicts(a1=True, a2=True, a3=False, b1=True)) == 1.0


def test_pass_rate_is_unweighted() -> None:
    # a1 ✓, a2 ✗, a3 MET ✗ (anti-pattern triggered), b1 ✓ → 2/4, ignoring the 2 and -3 weights
    assert scoring.pass_rate(_RUBRIC, _verdicts(a1=True, a2=False, a3=True, b1=True)) == 0.5


# --- axis_scores ----------------------------------------------------------------


def test_axis_scores_are_per_section() -> None:
    # Factual Accuracy: achievable 3 (2+1), achieved 2+0-3 = -1 → clamped 0.0
    # Presentation:     achievable 1, achieved 1                → 1.0
    axes = scoring.axis_scores(_RUBRIC, _verdicts(a1=True, a2=False, a3=True, b1=True))

    assert axes == {"Factual Accuracy": 0.0, "Presentation": 1.0}


# --- unjudged criteria ----------------------------------------------------------


def test_an_unjudged_criterion_drops_out_of_both_numerator_and_denominator() -> None:
    """INVARIANT: a missing verdict must not be scored as UNMET.

    Counting it as UNMET keeps its weight in the denominator, so a judge parse or transport
    failure would silently deflate the score in proportion to the failure rate — a benchmark
    that reports lower numbers when the harness is flaky.

    a2 (weight 1) has no verdict: denom drops 4→3, numerator 3→3 → 1.0, not 0.75.
    """
    judged = {"a1": True, "a3": False, "b1": True}

    assert scoring.score_case(_RUBRIC, [judged])["normalized_score"] == 1.0


def test_coverage_reports_the_judged_fraction() -> None:
    judged = {"a1": True, "a3": False, "b1": True}  # 3 of 4

    assert scoring.score_case(_RUBRIC, [judged])["coverage"] == 0.75


def _verdict(cid: str, status: str, case: int = 1, sequence: int = 1) -> dict[str, object]:
    raw = json.dumps({"explanation": "evidence", "criterion_status": status})
    return {
        "schema": "screamingface.criterion-verdict.v1",
        "case_id": case,
        "criterion_id": cid,
        "sequence": sequence,
        "producer_type": "model",
        "producer_id": "fixture-judge",
        "valid": True,
        "explanation": "evidence",
        "criterion_status": status,
        "raw_output": raw,
    }


def _invalid(cid: str, reason: str, case: int = 1, sequence: int = 1) -> dict[str, object]:
    return {
        "schema": "screamingface.criterion-verdict.v1",
        "case_id": case,
        "criterion_id": cid,
        "sequence": sequence,
        "producer_type": "model",
        "producer_id": "fixture-judge",
        "valid": False,
        "reason": reason,
        "raw_output": "not json",
    }


def _case_row(
    case: int,
    *per_criterion: tuple[str, list[str]],
    output: str | None = None,
) -> dict[str, object]:
    statuses = dict(per_criterion)
    evidence = {
        criterion_id: [
            _verdict(criterion_id, status, case, sequence)
            for sequence, status in enumerate(statuses[criterion_id], start=1)
        ]
        for criterion_id in ("a1", "a2", "a3", "b1")
    }
    return _case_row_from_evidence(case, evidence, output=output)


def _case_row_from_evidence(
    case: int,
    evidence: dict[str, list[dict[str, object]]],
    *,
    output: str | None = None,
) -> dict[str, object]:
    case_record = {
        "schema": CASE_SCHEMA,
        "case_id": case,
        "input": f"Question {case}",
        "output": output or f"Answer {case}",
        "finish_reason": "stop",
        "metadata": {},
    }
    criteria = []
    for index, criterion_id in enumerate(("a1", "a2", "a3", "b1")):
        criteria.append(
            bind_criterion_evaluation(
                case,
                case_record if index == 0 else None,
                {
                    "schema": CHECK_SCHEMA,
                    "case_id": case,
                    "criterion_id": criterion_id,
                    "criterion_type": "negative" if criterion_id == "a3" else "positive",
                    "requirement": f"Requirement {criterion_id}",
                },
                evidence[criterion_id],
            )
        )
    return bind_case_evaluation(case, criteria)


def test_candidate_output_cannot_become_judge_evidence() -> None:
    example = json.dumps(
        {
            "criterion_id": "<provided criterion_id>",
            "explanation": "Brief evidence for the verdict.",
            "criterion_status": "MET",
        }
    )
    result = agg.aggregate(
        json.dumps(
            [
                _case_row(
                    1,
                    ("a1", ["MET", "UNMET", "MET", "UNMET", "MET"]),
                    ("a2", ["MET", "UNMET", "MET", "UNMET", "MET"]),
                    ("a3", ["MET", "UNMET", "MET", "UNMET", "MET"]),
                    ("b1", ["MET", "UNMET", "MET", "UNMET", "MET"]),
                    output=example,
                )
            ]
        ),
        rubrics={1: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1),
    )

    assert result["metrics"]["n_runs"] == 5
    assert result["metrics"]["coverage"] == 1.0


def test_coverage_diagnostics_distinguish_invalid_and_missing_verdicts() -> None:
    evidence = {
        "a1": [_verdict("a1", "MET", sequence=n) for n in range(1, 6)],
        "a2": [_verdict("a2", "MET", sequence=n) for n in range(1, 6)],
        "a3": [
            *(_verdict("a3", "UNMET", sequence=n) for n in range(1, 5)),
            _invalid("a3", "invalid_json", sequence=5),
        ],
        # b1's fifth pass is absent: a transport/model call failed before binding.
        "b1": [_verdict("b1", "MET", sequence=n) for n in range(1, 5)],
    }

    result = agg.aggregate(
        json.dumps([_case_row_from_evidence(1, evidence)]),
        rubrics={1: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1),
    )

    assert {
        name: result["metrics"][name]
        for name in (
            "coverage",
            "coverage_target",
            "verdicts_expected",
            "verdicts_accepted",
            "verdicts_rejected",
            "verdicts_invalid",
            "verdicts_missing",
        )
    } == {
        "coverage": 0.9,
        "coverage_target": 0.95,
        "verdicts_expected": 20,
        "verdicts_accepted": 18,
        "verdicts_rejected": 2,
        "verdicts_invalid": 1,
        "verdicts_missing": 1,
    }


# --- judge_runs: per-run scoring, then the mean ----------------------------------


def test_runs_are_grouped_in_order_so_each_pass_scores_independently() -> None:
    """INVARIANT: the paper scores EACH judge pass, then means the passes (§4.2).

    Majority-voting the verdicts first would collapse disagreement before it reaches the score
    and would make the reported spread meaningless — the sd IS the judge-stability signal.
    """
    verdicts = [
        {"case_id": 1, "criterion_id": "a1", "sequence": n, "criterion_status": s}
        for n, s in enumerate(("MET", "UNMET", "MET"), start=1)
    ]

    per_run = agg.group_runs(verdicts)

    assert per_run == [{"a1": True}, {"a1": False}, {"a1": True}]


def test_a_criterion_with_fewer_passes_drops_out_of_the_missing_run() -> None:
    """A dropped judge pass must not become an UNMET — it leaves that run's rubric entirely."""
    verdicts = [
        {"case_id": 1, "criterion_id": "a1", "sequence": 1, "criterion_status": "MET"},
        {"case_id": 1, "criterion_id": "a1", "sequence": 2, "criterion_status": "MET"},
        {"case_id": 1, "criterion_id": "a2", "sequence": 1, "criterion_status": "MET"},
    ]

    per_run = agg.group_runs(verdicts)

    assert per_run == [{"a1": True, "a2": True}, {"a1": True}]


def test_score_case_means_the_runs_and_reports_the_spread() -> None:
    # run 1: a1 MET, a2 MET   → 3/4 = 0.75   (a1=2, a2=1, b1=1 positive; a3=-3)
    # run 2: a1 MET, a2 UNMET → 2/3 … restricted to judged criteria per run
    scored = scoring.score_case(
        _RUBRIC,
        [
            {"a1": True, "a2": True, "a3": False, "b1": True},
            {"a1": True, "a2": False, "a3": False, "b1": True},
        ],
    )

    assert scored["normalized_score"] == 0.875  # (1.0 + 0.75) / 2
    assert scored["normalized_score_sd"] == 0.125
    assert scored["n_runs"] == 2


def test_a_single_run_reports_zero_spread() -> None:
    scored = scoring.score_case(_RUBRIC, [{"a1": True, "a2": True, "a3": False, "b1": True}])

    assert scored["normalized_score"] == 1.0
    assert scored["normalized_score_sd"] == 0.0
    assert scored["n_runs"] == 1


# --- the whole reduction ---------------------------------------------------------


def test_aggregate_scores_the_official_nested_payload() -> None:
    rows = json.dumps(
        [
            _case_row(
                1,
                ("a1", ["MET"] * 5),
                ("a2", ["MET"] * 5),
                ("a3", ["UNMET"] * 5),
                ("b1", ["MET"] * 5),
            ),
            _case_row(
                2,
                ("a1", ["MET"] * 5),
                ("a2", ["UNMET"] * 5),
                ("a3", ["UNMET"] * 5),
                ("b1", ["UNMET"] * 5),
            ),
        ]
    )
    result = agg.aggregate(
        rows,
        rubrics={1: _RUBRIC, 2: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1, 2),
    )

    assert result["case_count"] == 2
    assert result["benchmark_revision"] == DRACO_REVISION
    assert result["score"] == 0.75  # case 1 → 1.0 · case 2 → 0.5
    assert "normalized_score" not in result["metrics"]
    assert [c["case_id"] for c in result["cases"]] == [1, 2]
    assert result["metrics"]["n_runs"] == 5
    assert result["failures"] == []


def test_a_case_id_missing_from_evidence_makes_the_case_unscored() -> None:
    """A scoreable verdict must carry the identity bound by the Engine after judging."""
    row = _case_row(
        1,
        ("a1", ["MET"] * 5),
        ("a2", ["MET"] * 5),
        ("a3", ["UNMET"] * 5),
        ("b1", ["MET"] * 5),
    )
    del row["evidence"][0]["case_id"]

    result = agg.aggregate(
        json.dumps([row]),
        rubrics={1: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1),
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None


def test_a_row_with_no_verdicts_is_a_failure_not_a_zero() -> None:
    rows = json.dumps(
        [
            _case_row(
                1,
                ("a1", ["MET"] * 5),
                ("a2", ["MET"] * 5),
                ("a3", ["UNMET"] * 5),
                ("b1", ["MET"] * 5),
            ),
            "judge refused",
        ]
    )
    result = agg.aggregate(
        rows,
        rubrics={1: _RUBRIC, 2: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1, 2),
    )

    assert result["case_count"] == 2
    assert result["failures"] == []
    assert result["cases"][1]["grade"] is None
    assert len(result["cases"][1]["failures"]) == 1
    assert result["cases"][0]["grade"]["score"] == 1.0
    assert result["score"] is None
    assert result["metrics"] == {}


def test_no_rows_at_all_is_an_execution_failure() -> None:
    """INVARIANT: a run with no evaluated Cases cannot report Candidate score zero."""
    with pytest.raises(agg.AggregateError, match="no DRACO rows"):
        agg.aggregate(
            "[]",
            rubrics={1: _RUBRIC},
            benchmark_id="draco",
            selected_cases=_selected_cases(1),
        )


def test_all_failed_rows_retain_the_collected_execution_error() -> None:
    rows = json.dumps(
        [
            {
                "error": {
                    "kind": "ResolutionError",
                    "message": "aigateway returned neither answer content nor tool calls",
                }
            }
        ]
    )

    result = agg.aggregate(
        rows,
        rubrics={1: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1),
    )

    assert result["score"] is None
    assert result["cases"][0]["failures"][0]["message"] == (
        "aigateway returned neither answer content nor tool calls"
    )


def test_a_valid_evaluated_case_may_legitimately_score_zero() -> None:
    rows = json.dumps(
        [
            _case_row(
                1,
                ("a1", ["UNMET"] * 5),
                ("a2", ["UNMET"] * 5),
                ("a3", ["MET"] * 5),
                ("b1", ["UNMET"] * 5),
            )
        ]
    )

    result = agg.aggregate(
        rows,
        rubrics={1: _RUBRIC},
        benchmark_id="draco",
        selected_cases=_selected_cases(1),
    )

    assert result["case_count"] == 1
    assert result["score"] == 0.0
    assert result["failures"] == []


def test_a_malformed_top_level_payload_raises() -> None:
    with pytest.raises(agg.AggregateError):
        agg.aggregate("not json", rubrics={}, benchmark_id="draco", selected_cases=[])


# --- where the rubrics come from -------------------------------------------------
#
# The [data] routes get absolute paths from `prepare --out`, so the rubrics path must come from
# the SAME deployment rather than a literal baked into url4.toml. A live local run hit exactly
# that: the config pinned the container path, the aggregate found no rubrics, and the run
# returned HTTP 200 with `failures:[{"reason":"unknown case_id"}]` — a success that scored
# nothing.


def test_missing_rubrics_directory_raises_rather_than_scoring_nothing(tmp_path) -> None:
    """INVARIANT: a misconfigured path is an ERROR, not an empty result.

    Returning {} makes every case an `unknown case_id` failure, which surfaces as a terminated
    run with a plausible-looking zero score. Failing here turns a silent misconfiguration into
    a loud one.
    """
    with pytest.raises(agg.AggregateError, match="no rubrics"):
        agg.load_rubrics(tmp_path / "absent")


def test_an_empty_rubrics_directory_raises(tmp_path) -> None:
    (tmp_path / "rubrics").mkdir()

    with pytest.raises(agg.AggregateError, match="no rubrics"):
        agg.load_rubrics(tmp_path / "rubrics")


def test_rubrics_load_keyed_by_case_id(tmp_path) -> None:
    (tmp_path / "7.json").write_text(json.dumps(_RUBRIC), encoding="utf-8")

    assert set(agg.load_rubrics(tmp_path)) == {7}
