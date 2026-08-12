"""The DRACO cross-row reducer — per-criterion verdicts in, Candidate Result out.

FEATURE: one url4 expression per Candidate ends in a cross-row reduce that turns every case's
judge verdicts into one scored result.
STORY: as a researcher, the number I publish is the DRACO paper's `normalized_score`.

Installed directly into each Runner world in the reducer position::

    (…iteration…)!/benchmarks/draco/<revision>/aggregate($rows)!'aggregate'

    context (row array)  →  the JSON array of every row's judge output
    intent ("aggregate") →  the fixed reduction operation

INVARIANT: the scoring formulas mirror `screamingface-benchmarks/benchmarking/graders/rubric.py`
(arXiv:2602.11685 §4.2) EXACTLY. Do not "improve" them. A different formula is a different
benchmark, and a leaderboard number computed here must mean what the paper says it means.

The expression this reducer serves runs the paper's `official` grading mode: ONE judge call per
CRITERION, five independent passes, and the judge blind to the weights and to the sibling
criteria. The Engine-owned Benchmark definition constructs that fan-out and this in-process
handler reduces the complete row collection without crossing an operating-system argv boundary.

AIDEV-NOTE: protocol caveats, the three ways a run here still differs from the paper:

* `judge_reasoning: "low"` (arXiv:2602.11685 §4.2) is NOT carried until the gateway supports it.
  `reasoning_effort` is absent from the OpenRouter plugin's rule set, and the gateway fails
  closed on an unknown parameter, so
  sending it would turn every judge call into a 400 rather than a deviation. `judge_temperature`
  and `max_tokens` DO reach the model.
* Candidate retrieval runs on the PROVIDER's search, not a backend this repo pins. Every lineup
  model is `openrouter/*`, so as of OME-797 (2026-08-12) all eight take the native mechanism,
  and OME-800 leaves the engine unset — OpenRouter picks its own built-in search where the model
  has one and Exa where it does not. So the search product can differ BETWEEN candidates of one
  run, and can change under us without a config edit.
  Before 2026-08-12 the mechanism was declared per route, and five candidates
  (`gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `kimi-k2.6`, `deepseek-v4-pro`,
  `qwen3.6-plus`) answered through the runner-driven Tavily loop instead. Runs either side of
  that date are not the same experiment.
* `EXCLUDED_DOMAINS` changes MEANING with the mechanism. The Tavily loop drops blocked hosts
  client-side (`runner.web_tools._is_blocked`) — the Runner enforces it. The native path only
  forwards `web_search_excluded_domains` and relies on the provider to honour it. Since the
  blocklist covers `arxiv.org`, `paperswithcode.com`, `semanticscholar.org` and `alphaxiv.org`
  — where the paper under reproduction lives — a native-path run rests on OpenRouter's
  compliance for its leakage control, which is not verified here.

None of the three is visible in the numbers this module emits. A score published as
"DRACO-reproduced" has to state all three.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from url4_cloud.benchmarks.contract import CandidateResult
from url4_cloud.benchmarks.draco import assets
from url4_cloud.benchmarks.draco import case_results as case_results_module
from url4_cloud.benchmarks.draco.case_evaluation import decode_case_evaluation
from url4_cloud.benchmarks.draco.definition import JUDGE_PASSES, REVISION
from url4_cloud.benchmarks.draco.errors import AggregateError as AggregateError
from url4_cloud.benchmarks.draco.scoring import flatten_criteria as flatten_criteria
from url4_cloud.benchmarks.draco.validation import optional_integer

COVERAGE_TARGET = case_results_module.COVERAGE_TARGET
VERDICT_SCHEMA = case_results_module.VERDICT_SCHEMA
group_runs = case_results_module.group_runs
valid_verdicts = case_results_module.valid_verdicts
load_rubrics = assets.load_rubrics


@dataclass(frozen=True)
class _DecodedRow:
    """One selected Case and its exact decoded evaluation, kept together."""

    raw: Any
    expected_case: Mapping[str, Any]
    evaluation: Mapping[str, Any] | None
    decode_error: str | None

    @property
    def case_records(self) -> Sequence[Mapping[str, Any]]:
        return [self.evaluation["case"]] if self.evaluation is not None else []

    @property
    def checks(self) -> Sequence[Mapping[str, Any]]:
        return self.evaluation["checks"] if self.evaluation is not None else []

    @property
    def evidence(self) -> Sequence[Mapping[str, Any]]:
        return self.evaluation["evidence"] if self.evaluation is not None else []


# --- the reduction ---------------------------------------------------------------


def aggregate(
    rows_json: str,
    rubrics: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
    *,
    selected_cases: Sequence[Mapping[str, Any]],
    judge_passes: int = JUDGE_PASSES,
    benchmark_revision: str = REVISION,
    criterion_count: int | None = None,
) -> dict[str, Any]:
    """Reduce the row array into a Candidate Result — one row per Case.

    INVARIANT: a case that produced no verdicts is never scored 0.0. Scoring it zero would
    penalise the Candidate for a harness failure, the same class of error as counting an unjudged
    criterion as UNMET. Instead the whole Candidate goes unscored: if ANY Case Result lacks a
    numeric grade, the result carries ``score: None`` and empty ``metrics``, so a partial run can
    never be mistaken for a complete one.

    The Case-scoped failure is attached to its own Case Result. Candidate-level ``failures`` stays
    empty by design — it is reserved for failures that cannot be attributed to a selected Case.
    """
    try:
        rows = json.loads(rows_json)
    except (TypeError, ValueError) as exc:
        raise AggregateError(f"reducer payload is not JSON: {exc}") from None
    if not isinstance(rows, list):
        raise AggregateError(f"reducer payload must be a JSON array, got {type(rows).__name__}")
    if isinstance(judge_passes, bool) or not isinstance(judge_passes, int) or judge_passes < 1:
        raise AggregateError("judge_passes must be a positive integer")
    if criterion_count is not None and (
        isinstance(criterion_count, bool)
        or not isinstance(criterion_count, int)
        or criterion_count < 1
    ):
        raise AggregateError("criterion_count must be a positive integer or None")
    # INVARIANT: absence of evaluated Cases is an execution failure, not Candidate score zero.
    if not rows:
        raise AggregateError("no DRACO Case results were collected; the Candidate cannot be scored")
    expected_cases = _validate_selected_cases(selected_cases, len(rows))

    decoded_rows = _decode_rows(rows, expected_cases, judge_passes)
    _require_verifiable_mapping(decoded_rows)
    case_results = _aggregate_rows(decoded_rows, rubrics, judge_passes, criterion_count)
    scored = [
        case
        for case in case_results
        if isinstance((grade := case.get("grade")), Mapping)
        and isinstance(grade.get("score"), int | float)
        and not isinstance(grade.get("score"), bool)
    ]
    if len(scored) != len(case_results):
        return CandidateResult(
            benchmark_id=benchmark_id,
            benchmark_revision=benchmark_revision,
            case_count=len(case_results),
            score=None,
            metrics={},
            cases=case_results,
            failures=[],
        ).as_payload()

    return CandidateResult(
        benchmark_id=benchmark_id,
        benchmark_revision=benchmark_revision,
        case_count=len(case_results),
        score=_mean_grades(scored, "score"),
        metrics={
            "normalized_score_sd": _mean_grade_metrics(scored, "normalized_score_sd"),
            "pass_rate": _mean_grade_metrics(scored, "pass_rate"),
            "pass_rate_sd": _mean_grade_metrics(scored, "pass_rate_sd"),
            "accuracy": _mean_optional_grade_metrics(scored, "accuracy"),
            "accuracy_pass_rate": _mean_optional_grade_metrics(scored, "accuracy_pass_rate"),
            "axis_scores": _mean_grade_metric_maps(scored, "axis_scores"),
            "axis_pass_rates": _mean_grade_metric_maps(scored, "axis_pass_rates"),
            "coverage": _mean_grade_metrics(scored, "coverage"),
            "coverage_sd": _mean_grade_metrics(scored, "coverage_sd"),
            "coverage_target": COVERAGE_TARGET,
            "n_runs": max((_grade_metric(case, "n_runs") for case in scored), default=0),
            "verdicts_expected": _sum_grade_metrics(scored, "verdicts_expected"),
            "verdicts_accepted": _sum_grade_metrics(scored, "verdicts_accepted"),
            "verdicts_rejected": _sum_grade_metrics(scored, "verdicts_rejected"),
            "verdicts_invalid": _sum_grade_metrics(scored, "verdicts_invalid"),
            "verdicts_missing": _sum_grade_metrics(scored, "verdicts_missing"),
        },
        cases=case_results,
        # Case-scoped failures live on their Case Result. Candidate-level failures are reserved
        # for failures that cannot be attributed to a selected Case.
        failures=[],
    ).as_payload()


def _decode_rows(
    rows: Sequence[Any],
    expected_cases: Sequence[Mapping[str, Any]],
    judge_passes: int,
) -> list[_DecodedRow]:
    decoded: list[_DecodedRow] = []
    for raw, expected_case in zip(rows, expected_cases, strict=True):
        try:
            evaluation = decode_case_evaluation(
                raw,
                int(expected_case["id"]),
                judge_passes=judge_passes,
            )
        except (TypeError, ValueError) as exc:
            evaluation = None
            error = str(exc)
        else:
            error = None
        decoded.append(_DecodedRow(raw, expected_case, evaluation, error))
    return decoded


def _aggregate_rows(
    decoded_rows: Sequence[_DecodedRow],
    rubrics: Mapping[int, Mapping[str, Any]],
    judge_passes: int,
    criterion_count: int | None,
) -> list[dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for index, row in enumerate(decoded_rows):
        if not row.case_records:
            failure = _row_failure(
                row.raw,
                index,
                row.expected_case,
                row.decode_error,
            )
            case_results.append(
                case_results_module.failed_selected_case_result(row.expected_case, failure)
            )
            continue
        case_record = row.case_records[0]
        case_id = optional_integer(case_record.get("case_id"))
        if case_id is None:  # pragma: no cover - sealed by _require_verifiable_mapping
            raise AssertionError("a scored DRACO row must carry its Engine-bound case_id")
        rubric = rubrics.get(case_id)
        if rubric is None:
            failure = {
                "stage": "grading",
                "code": "missing_case_rubric",
                "message": "the selected Case has no installed DRACO rubric",
                "retryable": None,
                "case_id": case_id,
                "metadata": {"row_index": index},
            }
            case_results.append(case_results_module.ungraded_case_result(case_record, failure))
            continue
        verdicts = case_results_module.valid_verdicts(rubric, row.evidence, case_id)
        if not verdicts:
            failure = {
                "stage": "grading",
                "code": "no_valid_judge_verdict",
                "message": "no valid Judge verdict was produced for this Case",
                "retryable": None,
                "case_id": case_id,
                "metadata": {"row_index": index},
            }
            case_results.append(
                case_results_module.incomplete_case_result(
                    case_record,
                    rubric,
                    row.checks,
                    row.evidence,
                    judge_passes,
                    criterion_count,
                    failure,
                )
            )
            continue
        case_results.append(
            case_results_module.scored_case_result(
                case_record,
                rubric,
                row.checks,
                row.evidence,
                verdicts,
                judge_passes,
                criterion_count,
            )
        )
    return case_results


def _row_failure(
    row: Any,
    index: int,
    expected_case: Mapping[str, Any],
    decode_error: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "row_index": index,
        **({"reason": " ".join(decode_error.split())[:200]} if decode_error else {}),
    }
    failure: dict[str, Any] = {
        "stage": "grading",
        "code": "invalid_case_evaluation",
        "message": "the Case produced no valid DRACO Case Evaluation",
        "retryable": None,
        "case_id": int(expected_case["id"]),
        "metadata": metadata,
    }
    error = row.get("error") if isinstance(row, Mapping) else None
    if not isinstance(error, Mapping):
        return failure
    metadata.clear()
    metadata["row_index"] = index
    selected = _bounded_error(error)
    failure.update(
        {
            "stage": "candidate",
            "code": selected.get("code", "case_execution_failed"),
            "message": selected.get("message", "Candidate Case execution failed"),
            "retryable": _retryable(error),
        }
    )
    if kind := selected.get("kind"):
        metadata["error_kind"] = kind
    return failure


def _bounded_error(error: Mapping[str, Any]) -> dict[str, str]:
    limits = {"kind": 80, "code": 80, "message": 200}
    return {
        field: " ".join(value.split())[:limit]
        for field, limit in limits.items()
        if isinstance((value := error.get(field)), str) and value.strip()
    }


def _retryable(error: Mapping[str, Any]) -> bool | None:
    if isinstance(value := error.get("retryable"), bool):
        return value
    if isinstance(permanent := error.get("permanent"), bool):
        return not permanent
    return None


def _require_verifiable_mapping(rows: Sequence[_DecodedRow]) -> None:
    """Require one unique Engine-bound Case identity for every scoreable row."""

    claimed: dict[int, int] = {}
    for index, row in enumerate(rows):
        case_records = row.case_records
        check_records = row.checks
        verdicts = row.evidence
        if not case_records and not verdicts:
            continue
        if len(case_records) != 1:
            raise AggregateError(
                f"Case result at position {index} must carry exactly one Engine-bound Case record; "
                f"found {len(case_records)}"
            )
        ids = [
            optional_integer(record.get("case_id"))
            for record in (*case_records, *check_records, *verdicts)
        ]
        if any(case_id is None for case_id in ids):
            raise AggregateError(
                f"Case result at position {index} has a verdict without an Engine-bound case_id"
            )
        unique = {case_id for case_id in ids if case_id is not None}
        if len(unique) != 1:
            raise AggregateError(
                f"Case result at position {index} carries multiple case_id values {sorted(unique)}"
            )
        case_id = unique.pop()
        previous = claimed.get(case_id)
        if previous is not None:
            raise AggregateError(
                f"duplicate case_id {case_id} appears at Case result positions "
                f"{previous} and {index}"
            )
        expected_id = int(row.expected_case["id"])
        if case_id != expected_id:
            raise AggregateError(
                f"Case result at position {index} claims case_id {case_id}, "
                f"but the selected Case is {expected_id}"
            )
        claimed[case_id] = index


def _validate_selected_cases(
    selected_cases: Sequence[Mapping[str, Any]], row_count: int
) -> list[Mapping[str, Any]]:
    if len(selected_cases) != row_count:
        raise AggregateError(
            f"selected Case sequence must exactly match the {row_count} collected Case results; "
            f"got {len(selected_cases)} selections"
        )
    expected = list(selected_cases)
    ids: set[int] = set()
    for index, case in enumerate(expected):
        case_id = optional_integer(case.get("id")) if isinstance(case, Mapping) else None
        input_value = case.get("input") if isinstance(case, Mapping) else None
        if case_id is None or case_id < 1 or not isinstance(input_value, str) or not input_value:
            raise AggregateError(f"selected Case {index} must carry a positive id and input text")
        if case_id in ids:
            raise AggregateError(f"selected Case sequence repeats case_id {case_id}")
        ids.add(case_id)
    return expected


def _grade(case: Mapping[str, Any]) -> Mapping[str, Any]:
    grade = case.get("grade")
    if not isinstance(grade, Mapping):  # pragma: no cover - selected by caller
        raise AssertionError("scored Case must carry a Case Grade")
    return grade


def _grade_metric(case: Mapping[str, Any], key: str) -> Any:
    metrics = _grade(case).get("metrics")
    if not isinstance(metrics, Mapping):  # pragma: no cover - constructed locally
        raise AssertionError("Case Grade must carry metrics")
    return metrics[key]


def _mean_grades(cases: Sequence[Mapping[str, Any]], key: str) -> float:
    return round(sum(float(_grade(case)[key]) for case in cases) / len(cases), 4)


def _mean_grade_metrics(cases: Sequence[Mapping[str, Any]], key: str) -> float:
    return round(sum(float(_grade_metric(case, key)) for case in cases) / len(cases), 4)


def _mean_optional_grade_metrics(cases: Sequence[Mapping[str, Any]], key: str) -> float | None:
    """Mean over the Cases that reported ``key``, or ``None`` when none of them did.

    A Case whose rubric has no Factual Accuracy axis reports ``None`` rather than 0.0, so it must
    be skipped instead of dragging the Candidate mean toward zero. This mirrors how
    :func:`_mean_grade_metric_maps` averages each axis over the Cases that carry it.
    """
    values = [
        float(value)
        for case in cases
        if (value := _grade_metric(case, key)) is not None and not isinstance(value, bool)
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _sum_grade_metrics(cases: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(int(_grade_metric(case, key)) for case in cases)


def _mean_grade_metric_maps(cases: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for case in cases:
        metric = _grade_metric(case, key)
        if not isinstance(metric, Mapping):  # pragma: no cover - constructed locally
            raise AssertionError(f"Case Grade metric {key!r} must be an object")
        for name, value in metric.items():
            values.setdefault(str(name), []).append(float(value))
    return {name: round(sum(items) / len(items), 4) for name, items in sorted(values.items())}
