"""Install canonical DRACO's private assets and functions into one Runner world."""

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
from url4_cloud.benchmarks.draco.check_policy import DRACO_CHECK
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
    REVISION,
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


def install(node: Url4Node, root: Path) -> None:
    """Register the routes referenced by canonical DRACO."""
    cases_json, selected_cases, rubrics = _protocol_assets(root)
    node.data(CASES_ROUTE, cases_json, media_type="application/json")
    node.endpoint(TASKS_ROUTE)(_task_rows(root))
    # The mid-run check surface the corrective loop consumes. It closes over `node` so the
    # judge route resolves per request — installation must still work in a world that holds
    # no model routes at all (every benchmark-only test builds one).
    node.endpoint(CHECK_SURFACE_ROUTE)(
        check_surface(
            node,
            root,
            DRACO_CHECK,
        )
    )
    node.endpoint(VERDICT_ROUTE)(_criterion_verdict)
    node.endpoint(CRITERION_EVALUATION_ROUTE)(_criterion_evaluation)
    node.endpoint(CASE_EVALUATION_ROUTE)(
        case_evaluation_endpoint(
            label="DRACO Case evaluation",
            item_name="Criterion evaluation",
            bind=bind_case_evaluation,
        )
    )
    node.endpoint(AGGREGATE_ROUTE)(
        aggregate_endpoint(
            label="DRACO",
            available_case_count=len(selected_cases),
            aggregate=_aggregate(
                selected_cases,
                rubrics,
            ),
        )
    )


def _protocol_assets(
    root: Path,
) -> tuple[str, list[dict[str, object]], dict[int, dict[str, Any]]]:
    """Load and validate canonical DRACO before registering any route."""

    raw = _read(root / "cases.json", "DRACO cases")
    selected = _parse_cases(raw)
    if len(selected) != CASE_COUNT:
        raise _unavailable(f"expected {CASE_COUNT} canonical DRACO cases, got {len(selected)}")
    try:
        rubrics = protocol_assets.validate_protocol_assets(root, selected)
    except (OSError, ValueError) as exc:
        raise _unavailable(str(exc)) from exc
    return (
        json.dumps(selected, ensure_ascii=False, separators=(",", ":")),
        selected,
        rubrics,
    )


def _task_rows(
    root: Path,
):
    def task_rows(request: Request) -> str:
        try:
            case_id = tasks.positive_case_id(request.intent)
            answer = candidate_answer(request.context)
            evaluator_text = answer.text
            raw_cases = _read(root / "cases.json", "DRACO cases")
            criteria = tasks.load_criteria(root / "criteria", case_id)
            rubric = json_object(
                _read(root / "rubrics" / f"{case_id}.json", f"DRACO Case {case_id} rubric"),
                f"DRACO Case {case_id} rubric",
            )
            selected = list(rubric_scoring.flatten_criteria(rubric))
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
                candidate=answer,
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


def _criterion_evaluation(request: Request) -> str:
    try:
        case_id = tasks.positive_case_id(request.intent)
        payload = json_object(request.context, "DRACO Criterion evaluation")
        expected = (
            "case",
            "check",
            *(f"evidence_{sequence}" for sequence in range(1, JUDGE_PASSES + 1)),
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


def _aggregate(
    selected_cases: list[dict[str, object]],
    rubrics: dict[int, dict[str, Any]],
):
    def aggregate(case_evaluations: str, selected_case_count: int) -> dict[str, Any]:
        return scoring.aggregate(
            case_evaluations,
            rubrics,
            BENCHMARK_ID,
            selected_cases=selected_cases[:selected_case_count],
            judge_passes=JUDGE_PASSES,
            benchmark_revision=REVISION,
        )

    return aggregate


def _parse_cases(raw: str) -> list[dict[str, object]]:
    try:
        cases = json.loads(raw)
        if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
            raise ValueError("expected a JSON array of objects")
        return cases
    except (TypeError, ValueError) as exc:
        raise _unavailable(f"could not read canonical DRACO cases: {exc}") from exc


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _unavailable(f"could not read {label} at {str(path)!r}: {exc}") from exc


__all__ = ["install"]
