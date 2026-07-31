"""DRACO aggregation — the paper's exact scoring math.

FEATURE: the cross-row reducer of a Candidate benchmark run turns per-criterion judge verdicts
into a `CandidateResult`.
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


# --- normalized_score -----------------------------------------------------------


def test_perfect_answer_scores_one() -> None:
    # a1+a2+b1 MET (2+1+1=4), a3 UNMET → 4/4
    v = _verdicts(a1=True, a2=True, a3=False, b1=True)

    assert agg.normalized_score(_RUBRIC, v) == 1.0


def test_a_met_negative_criterion_subtracts_from_the_numerator() -> None:
    # 2 + 0 + (-3) + 1 = 0 over denom 4 → 0.0
    v = _verdicts(a1=True, a2=False, a3=True, b1=True)

    assert agg.normalized_score(_RUBRIC, v) == 0.0


def test_the_score_is_clamped_at_zero_not_negative() -> None:
    # 0 + 0 + (-3) + 0 = -3 over 4 → clamped to 0.0, never -0.75
    v = _verdicts(a1=False, a2=False, a3=True, b1=False)

    assert agg.normalized_score(_RUBRIC, v) == 0.0


def test_partial_credit_is_weight_aware() -> None:
    # a1 only: 2/4
    assert agg.normalized_score(_RUBRIC, _verdicts(a1=True, a2=False, a3=False, b1=False)) == 0.5


def test_all_negative_rubric_returns_zero_rather_than_dividing_by_zero() -> None:
    """The paper does not define this case; returning 0.0 beats inventing a formula."""
    rubric = {"sections": [{"id": "X", "criteria": [{"id": "n1", "weight": -1}]}]}

    assert agg.normalized_score(rubric, {"n1": False}) == 0.0


# --- pass_rate ------------------------------------------------------------------


def test_pass_rate_counts_avoided_negatives_as_correct() -> None:
    # a1 MET ✓, a2 MET ✓, a3 UNMET ✓ (anti-pattern avoided), b1 MET ✓ → 4/4
    assert agg.pass_rate(_RUBRIC, _verdicts(a1=True, a2=True, a3=False, b1=True)) == 1.0


def test_pass_rate_is_unweighted() -> None:
    # a1 ✓, a2 ✗, a3 MET ✗ (anti-pattern triggered), b1 ✓ → 2/4, ignoring the 2 and -3 weights
    assert agg.pass_rate(_RUBRIC, _verdicts(a1=True, a2=False, a3=True, b1=True)) == 0.5


# --- axis_scores ----------------------------------------------------------------


def test_axis_scores_are_per_section() -> None:
    # Factual Accuracy: achievable 3 (2+1), achieved 2+0-3 = -1 → clamped 0.0
    # Presentation:     achievable 1, achieved 1                → 1.0
    axes = agg.axis_scores(_RUBRIC, _verdicts(a1=True, a2=False, a3=True, b1=True))

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

    assert agg.score_case(_RUBRIC, [judged])["normalized_score"] == 1.0


def test_coverage_reports_the_judged_fraction() -> None:
    judged = {"a1": True, "a3": False, "b1": True}  # 3 of 4

    assert agg.score_case(_RUBRIC, [judged])["coverage"] == 0.75


# --- harvesting verdicts out of the nested payload -------------------------------
#
# The reducer receives ONE string per case, prose-wrapped once per nesting level:
#
#   "case\n\ngraded: [\"criterion\\n\\ncrit: a1\\nruns: [{…}, {…}, {…}]\", …]"
#
# INVARIANT: the aggregator NEVER parses that scaffolding. It harvests the JSON verdict
# objects and ignores everything between them. Prose framing is an engine formatting detail
# that has already changed once; a regex over it would be a silent-breakage contract.


def _verdict(cid: str, status: str, case: int = 1) -> str:
    return json.dumps({"case_id": case, "criterion_id": cid, "criterion_status": status})


def _case_row(case: int, *per_criterion: tuple[str, list[str]]) -> str:
    """Rebuild the engine's real nesting: case → criteria → runs."""
    crits = [
        "criterion\\n\\ncrit: {}\\nruns: [{}]".format(
            cid, ", ".join(_verdict(cid, s, case) for s in st)
        )
        for cid, st in per_criterion
    ]
    return "case\n\ngraded: [{}]".format(", ".join(json.dumps(c) for c in crits))


def test_verdicts_are_harvested_from_the_nested_prose() -> None:
    row = _case_row(1, ("a1", ["MET", "MET", "MET"]))

    harvested = agg.harvest_verdicts(row)

    assert harvested == [{"case_id": 1, "criterion_id": "a1", "criterion_status": "MET"}] * 3


def test_harvesting_ignores_json_without_a_criterion_status() -> None:
    """Only verdicts count — a stray object in the prose must not become one."""
    row = 'case\n\nnote: {{"id": "not-a-verdict"}}\ngraded: [{}]'.format(
        json.dumps("runs: [{}]".format(_verdict("a1", "MET")))
    )

    assert [v["criterion_id"] for v in agg.harvest_verdicts(row)] == ["a1"]


def test_a_fenced_verdict_is_still_harvested() -> None:
    row = 'runs: ["```json\\n{}\\n```"]'.format(_verdict("a1", "MET").replace('"', '\\"'))

    assert len(agg.harvest_verdicts(row)) == 1


def test_no_verdicts_at_all_yields_an_empty_list() -> None:
    assert agg.harvest_verdicts("case\n\ngraded: I could not grade this.") == []


# --- judge_runs: per-run scoring, then the mean ----------------------------------


def test_runs_are_grouped_in_order_so_each_pass_scores_independently() -> None:
    """INVARIANT: the paper scores EACH judge pass, then means the passes (§4.2).

    Majority-voting the verdicts first would collapse disagreement before it reaches the score
    and would make the reported spread meaningless — the sd IS the judge-stability signal.
    """
    verdicts = [
        {"case_id": 1, "criterion_id": "a1", "criterion_status": s} for s in ("MET", "UNMET", "MET")
    ]

    per_run = agg.group_runs(verdicts)

    assert per_run == [{"a1": True}, {"a1": False}, {"a1": True}]


def test_a_criterion_with_fewer_passes_drops_out_of_the_missing_run() -> None:
    """A dropped judge pass must not become an UNMET — it leaves that run's rubric entirely."""
    verdicts = [
        {"case_id": 1, "criterion_id": "a1", "criterion_status": "MET"},
        {"case_id": 1, "criterion_id": "a1", "criterion_status": "MET"},
        {"case_id": 1, "criterion_id": "a2", "criterion_status": "MET"},
    ]

    per_run = agg.group_runs(verdicts)

    assert per_run == [{"a1": True, "a2": True}, {"a1": True}]


def test_score_case_means_the_runs_and_reports_the_spread() -> None:
    # run 1: a1 MET, a2 MET   → 3/4 = 0.75   (a1=2, a2=1, b1=1 positive; a3=-3)
    # run 2: a1 MET, a2 UNMET → 2/3 … restricted to judged criteria per run
    scored = agg.score_case(
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
    scored = agg.score_case(_RUBRIC, [{"a1": True, "a2": True, "a3": False, "b1": True}])

    assert scored["normalized_score"] == 1.0
    assert scored["normalized_score_sd"] == 0.0
    assert scored["n_runs"] == 1


# --- the whole reduction ---------------------------------------------------------


def test_aggregate_scores_the_official_nested_payload() -> None:
    rows = json.dumps(
        [
            _case_row(
                1,
                ("a1", ["MET"] * 3),
                ("a2", ["MET"] * 3),
                ("a3", ["UNMET"] * 3),
                ("b1", ["MET"] * 3),
            ),
            _case_row(
                2,
                ("a1", ["MET"] * 3),
                ("a2", ["UNMET"] * 3),
                ("a3", ["UNMET"] * 3),
                ("b1", ["UNMET"] * 3),
            ),
        ]
    )
    result = agg.aggregate(rows, rubrics={1: _RUBRIC, 2: _RUBRIC}, benchmark_id="draco")

    assert result["case_count"] == 2
    assert result["score"] == 0.75  # case 1 → 1.0 · case 2 → 0.5
    assert [c["case_id"] for c in result["case_results"]] == [1, 2]
    assert result["metrics"]["n_runs"] == 3
    assert result["failures"] == []


def test_a_case_id_missing_from_the_verdicts_falls_back_to_row_position() -> None:
    """The judge echoes the id, but an LLM can drop it — position is the benchmark's own
    knowledge and is stable because `on_error=collect` preserves row order."""
    row = "runs: [{}]".format(json.dumps({"criterion_id": "a1", "criterion_status": "MET"}))

    result = agg.aggregate(json.dumps([row]), rubrics={1: _RUBRIC}, benchmark_id="draco")

    assert result["case_results"][0]["case_id"] == 1


def test_a_row_with_no_verdicts_is_a_failure_not_a_zero() -> None:
    rows = json.dumps([_case_row(1, ("a1", ["MET"])), "case\n\ngraded: judge refused"])
    result = agg.aggregate(rows, rubrics={1: _RUBRIC, 2: _RUBRIC}, benchmark_id="draco")

    assert result["case_count"] == 1
    assert len(result["failures"]) == 1
    assert result["score"] == 1.0


def test_no_rows_at_all_yields_a_zero_result_rather_than_an_exception() -> None:
    result = agg.aggregate("[]", rubrics={1: _RUBRIC}, benchmark_id="draco")

    assert result["case_count"] == 0
    assert result["score"] == 0.0


def test_a_malformed_top_level_payload_raises() -> None:
    with pytest.raises(agg.AggregateError):
        agg.aggregate("not json", rubrics={}, benchmark_id="draco")


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


def test_the_rubrics_path_defaults_to_the_environment(tmp_path, monkeypatch) -> None:
    """One source of truth per deployment: the image sets it, a local run overrides it."""
    (tmp_path / "1.json").write_text(json.dumps(_RUBRIC), encoding="utf-8")
    monkeypatch.setenv("URL4_BENCHMARK_RUBRICS", str(tmp_path))

    assert agg.rubrics_dir(None) == tmp_path


def test_an_explicit_path_beats_the_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("URL4_BENCHMARK_RUBRICS", "/env/path")

    assert agg.rubrics_dir(tmp_path) == tmp_path


def test_without_either_it_falls_back_to_the_image_default(monkeypatch) -> None:
    monkeypatch.delenv("URL4_BENCHMARK_RUBRICS", raising=False)

    assert str(agg.rubrics_dir(None)) == agg.DEFAULT_RUBRICS_DIR
