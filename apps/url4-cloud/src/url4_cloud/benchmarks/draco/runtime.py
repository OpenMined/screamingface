"""Install DRACO's private assets and deterministic functions into one Runner world.

INVARIANT: a profile validates its complete selected Case/criteria/rubric set before any of its
routes are registered, so an executable world can never expose a half-installed DRACO protocol.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.draco import aggregate as scoring
from url4_cloud.benchmarks.draco import assets as protocol_assets
from url4_cloud.benchmarks.draco import records, tasks
from url4_cloud.benchmarks.draco import scoring as rubric_scoring
from url4_cloud.benchmarks.draco.case_evaluation import (
    bind_case_evaluation,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.check_policy import draco_check
from url4_cloud.benchmarks.draco.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASE_COUNT,
    CASE_EVALUATION_ROUTE,
    CASES_ROUTE,
    CHECK_SURFACE_ROUTE,
    CRITERION_EVALUATION_ROUTE,
    JUDGE_MODEL,
    JUDGE_PASSES,
    LITE_AGGREGATE_ROUTE,
    LITE_BENCHMARK_ID,
    LITE_CASE_COUNT,
    LITE_CASE_EVALUATION_ROUTE,
    LITE_CASE_IDS,
    LITE_CASES_ROUTE,
    LITE_CHECK_SURFACE_ROUTE,
    LITE_CRITERION_COUNT,
    LITE_CRITERION_EVALUATION_ROUTE,
    LITE_CRITERION_SELECTION,
    LITE_JUDGE_PASSES,
    LITE_REVISION,
    LITE_TASKS_ROUTE,
    LITE_VERDICT_ROUTE,
    REVISION,
    SMOKE_AGGREGATE_ROUTE,
    SMOKE_BENCHMARK_ID,
    SMOKE_CASE_COUNT,
    SMOKE_CASE_EVALUATION_ROUTE,
    SMOKE_CASES_ROUTE,
    SMOKE_CHECK_SURFACE_ROUTE,
    SMOKE_CRITERION_COUNT,
    SMOKE_CRITERION_EVALUATION_ROUTE,
    SMOKE_JUDGE_PASSES,
    SMOKE_REVISION,
    SMOKE_TASKS_ROUTE,
    SMOKE_VERDICT_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
)
from url4_cloud.benchmarks.draco.verdict import bind, binding_key
from url4_cloud.benchmarks.evaluation import (
    aggregate_endpoint,
    candidate_answer,
    case_evaluation_endpoint,
    compact_json,
    json_object,
)
from url4_cloud.benchmarks.evaluation import benchmark_unavailable as _unavailable
from url4_cloud.benchmarks.rubric_check import check_surface


def install_canonical(node: Url4Node, root: Path) -> None:
    """Register the routes referenced by canonical DRACO."""
    _install_protocol(
        node,
        root,
        cases_route=CASES_ROUTE,
        tasks_route=TASKS_ROUTE,
        verdict_route=VERDICT_ROUTE,
        criterion_evaluation_route=CRITERION_EVALUATION_ROUTE,
        case_evaluation_route=CASE_EVALUATION_ROUTE,
        aggregate_route=AGGREGATE_ROUTE,
        check_surface_route=CHECK_SURFACE_ROUTE,
        benchmark_id=BENCHMARK_ID,
        benchmark_revision=REVISION,
        declared_case_count=CASE_COUNT,
        judge_passes=JUDGE_PASSES,
        criterion_count=None,
        criterion_selection="all",
        case_ids=None,
    )


def install_lite(node: Url4Node, root: Path) -> None:
    """Register the routes referenced by DRACO Lite."""
    _install_protocol(
        node,
        root,
        cases_route=LITE_CASES_ROUTE,
        tasks_route=LITE_TASKS_ROUTE,
        verdict_route=LITE_VERDICT_ROUTE,
        criterion_evaluation_route=LITE_CRITERION_EVALUATION_ROUTE,
        case_evaluation_route=LITE_CASE_EVALUATION_ROUTE,
        aggregate_route=LITE_AGGREGATE_ROUTE,
        check_surface_route=LITE_CHECK_SURFACE_ROUTE,
        benchmark_id=LITE_BENCHMARK_ID,
        benchmark_revision=LITE_REVISION,
        declared_case_count=LITE_CASE_COUNT,
        judge_passes=LITE_JUDGE_PASSES,
        criterion_count=LITE_CRITERION_COUNT,
        criterion_selection=LITE_CRITERION_SELECTION,
        case_ids=LITE_CASE_IDS,
    )


def install_smoke(node: Url4Node, root: Path) -> None:
    """Register the routes referenced by DRACO Smoke."""
    _install_protocol(
        node,
        root,
        cases_route=SMOKE_CASES_ROUTE,
        tasks_route=SMOKE_TASKS_ROUTE,
        verdict_route=SMOKE_VERDICT_ROUTE,
        criterion_evaluation_route=SMOKE_CRITERION_EVALUATION_ROUTE,
        case_evaluation_route=SMOKE_CASE_EVALUATION_ROUTE,
        aggregate_route=SMOKE_AGGREGATE_ROUTE,
        check_surface_route=SMOKE_CHECK_SURFACE_ROUTE,
        benchmark_id=SMOKE_BENCHMARK_ID,
        benchmark_revision=SMOKE_REVISION,
        declared_case_count=SMOKE_CASE_COUNT,
        judge_passes=SMOKE_JUDGE_PASSES,
        criterion_count=SMOKE_CRITERION_COUNT,
        criterion_selection="prefix",
        case_ids=(1,),
    )


def _install_protocol(
    node: Url4Node,
    root: Path,
    *,
    cases_route: str,
    tasks_route: str,
    verdict_route: str,
    criterion_evaluation_route: str,
    case_evaluation_route: str,
    aggregate_route: str,
    check_surface_route: str,
    benchmark_id: str,
    benchmark_revision: str,
    declared_case_count: int,
    judge_passes: int,
    criterion_count: int | None,
    criterion_selection: rubric_scoring.CriterionSelection,
    case_ids: tuple[int, ...] | None,
) -> None:
    """Register one DRACO multiplicity profile over the shared pinned assets."""

    cases_json, selected_cases, rubrics = _protocol_assets(
        root,
        case_ids,
        declared_case_count,
        criterion_count,
        criterion_selection,
    )
    node.data(cases_route, cases_json, media_type="application/json")
    node.endpoint(tasks_route)(_task_rows(root, criterion_count, criterion_selection))
    # The mid-run check surface the corrective loop consumes. It closes over `node` so the
    # judge route resolves per request — installation must still work in a world that holds
    # no model routes at all (every benchmark-only test builds one).
    node.endpoint(check_surface_route)(
        check_surface(
            node,
            root,
            draco_check(criterion_count=criterion_count, selection=criterion_selection),
        )
    )
    node.endpoint(verdict_route)(_criterion_verdict)
    node.endpoint(criterion_evaluation_route)(_criterion_evaluation(judge_passes))
    node.endpoint(case_evaluation_route)(
        case_evaluation_endpoint(
            label="DRACO Case evaluation",
            item_name="Criterion evaluation",
            bind=bind_case_evaluation,
        )
    )
    node.endpoint(aggregate_route)(
        aggregate_endpoint(
            label="DRACO",
            available_case_count=len(selected_cases),
            aggregate=_aggregate(
                benchmark_id,
                benchmark_revision,
                judge_passes,
                criterion_count,
                selected_cases,
                rubrics,
            ),
        )
    )


def _protocol_assets(
    root: Path,
    case_ids: tuple[int, ...] | None,
    declared_case_count: int,
    criterion_count: int | None,
    criterion_selection: rubric_scoring.CriterionSelection,
) -> tuple[str, list[dict[str, object]], dict[int, dict[str, Any]]]:
    """Load and validate one complete profile before registering any route."""

    raw = _read(root / "cases.json", "DRACO cases")
    selected = _select_cases(raw, case_ids)
    if len(selected) != declared_case_count:
        raise _unavailable(
            f"expected {declared_case_count} DRACO cases for this profile, got {len(selected)}"
        )
    try:
        rubrics = protocol_assets.validate_protocol_assets(
            root, selected, criterion_count, criterion_selection
        )
    except (OSError, ValueError) as exc:
        raise _unavailable(str(exc)) from exc
    return (
        json.dumps(selected, ensure_ascii=False, separators=(",", ":")),
        selected,
        rubrics,
    )


def _task_rows(
    root: Path,
    criterion_count: int | None,
    criterion_selection: rubric_scoring.CriterionSelection,
):
    def task_rows(request: Request) -> str:
        try:
            case_id = tasks.positive_case_id(request.intent)
            answer = candidate_answer(request.context)
            evaluator_text, finish_reason = answer.text, answer.finish_reason
            raw_cases = _read(root / "cases.json", "DRACO cases")
            criteria = tasks.load_criteria(root / "criteria", case_id)
            rubric = json_object(
                _read(root / "rubrics" / f"{case_id}.json", f"DRACO Case {case_id} rubric"),
                f"DRACO Case {case_id} rubric",
            )
            selected = rubric_scoring.select_criteria(
                rubric,
                criterion_count,
                criterion_selection,
            )
            criteria_by_id = {str(criterion.get("id")): criterion for criterion in criteria}
            selected_criteria = [criteria_by_id[str(criterion["id"])] for criterion in selected]
            result = tasks.build_tasks(
                case_id,
                tasks.load_question(root / "criteria", case_id),
                evaluator_text,
                selected_criteria,
            )
            case_record = records.bind_case(
                raw_cases,
                case_id=case_id,
                answer=evaluator_text,
                output=answer.output,
                refusal=answer.refusal,
                finish_reason=finish_reason,
            )
            for index, row in enumerate(result):
                row["case_record"] = (
                    json.dumps(case_record, ensure_ascii=False, separators=(",", ":"))
                    if index == 0
                    else "{}"
                )
                row["check_record"] = json.dumps(
                    records.bind_check(
                        row["criterion"],
                        case_id=case_id,
                        criterion_id=row["criterion_id"],
                        criterion_type=row["criterion_type"],
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return compact_json(result)

    return task_rows


def _criterion_verdict(request: Request) -> str:
    try:
        case_id, sequence, criterion_id = binding_key(request.intent)
        record = bind(
            request.context,
            case_id=case_id,
            criterion_id=criterion_id,
            sequence=sequence,
            producer_id=JUDGE_MODEL,
        )
    except ValueError as exc:
        raise _unavailable(str(exc)) from exc
    return compact_json(record)


def _criterion_evaluation(judge_passes: int):
    def criterion_evaluation(request: Request) -> str:
        try:
            case_id = tasks.positive_case_id(request.intent)
            payload = json_object(request.context, "DRACO Criterion evaluation")
            expected = (
                "case",
                "check",
                *(f"evidence_{sequence}" for sequence in range(1, judge_passes + 1)),
            )
            if tuple(payload) != expected:
                raise ValueError(
                    "DRACO Criterion evaluation fields must be case, check, and consecutive "
                    "evidence_1..evidence_N"
                )
            raw_case = json_object(payload["case"], "Case record")
            case_record = raw_case or None
            check_record = json_object(payload["check"], "Check record")
            evidence = [
                json_object(payload[field], field)
                for field in expected
                if field.startswith("evidence_")
            ]
            result = bind_criterion_evaluation(
                case_id,
                case_record,
                check_record,
                evidence,
            )
        except (TypeError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return compact_json(result)

    return criterion_evaluation


def _aggregate(
    benchmark_id: str,
    benchmark_revision: str,
    judge_passes: int,
    criterion_count: int | None,
    selected_cases: list[dict[str, object]],
    rubrics: dict[int, dict[str, Any]],
):
    def aggregate(case_evaluations: str, selected_case_count: int) -> dict[str, Any]:
        return scoring.aggregate(
            case_evaluations,
            rubrics,
            benchmark_id,
            selected_cases=selected_cases[:selected_case_count],
            judge_passes=judge_passes,
            benchmark_revision=benchmark_revision,
            criterion_count=criterion_count,
        )

    return aggregate


def _select_cases(raw: str, case_ids: tuple[int, ...] | None) -> list[dict[str, object]]:
    try:
        cases = json.loads(raw)
        if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
            raise ValueError("expected a JSON array of objects")
        if case_ids is None:
            return cases
        by_id = {case["id"]: case for case in cases}
        return [by_id[case_id] for case_id in case_ids]
    except (KeyError, TypeError, ValueError) as exc:
        raise _unavailable(f"could not select DRACO cases {case_ids}: {exc}") from exc


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _unavailable(f"could not read {label} at {str(path)!r}: {exc}") from exc


__all__ = ["install_canonical", "install_lite", "install_smoke"]
