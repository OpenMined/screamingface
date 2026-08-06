"""Install DRACO's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from pathlib import Path

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.contract import decode_candidate_invocation
from url4_cloud.benchmarks.draco import aggregate as scoring
from url4_cloud.benchmarks.draco import records, tasks
from url4_cloud.benchmarks.draco.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASES_ROUTE,
    JUDGE_MODEL,
    JUDGE_PASSES,
    LITE_AGGREGATE_ROUTE,
    LITE_BENCHMARK_ID,
    LITE_CASE_IDS,
    LITE_CASES_ROUTE,
    LITE_CRITERION_COUNT,
    LITE_JUDGE_PASSES,
    LITE_REVISION,
    LITE_TASKS_ROUTE,
    LITE_VERDICT_ROUTE,
    REVISION,
    SMOKE_AGGREGATE_ROUTE,
    SMOKE_BENCHMARK_ID,
    SMOKE_CASES_ROUTE,
    SMOKE_CRITERION_COUNT,
    SMOKE_JUDGE_PASSES,
    SMOKE_REVISION,
    SMOKE_TASKS_ROUTE,
    SMOKE_VERDICT_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
)
from url4_cloud.benchmarks.draco.verdict import bind, binding_key


def install(node: Url4Node, root: Path) -> None:
    """Register every route referenced by the DRACO expression.

    Providers read lazily so a general-purpose Runner can carry the installed definition without
    requiring DRACO's private image assets until an expression actually selects DRACO.
    """

    _install_protocol(
        node,
        root,
        cases_route=CASES_ROUTE,
        tasks_route=TASKS_ROUTE,
        verdict_route=VERDICT_ROUTE,
        aggregate_route=AGGREGATE_ROUTE,
        benchmark_id=BENCHMARK_ID,
        benchmark_revision=REVISION,
        judge_passes=JUDGE_PASSES,
        criterion_count=None,
        case_ids=None,
    )
    _install_protocol(
        node,
        root,
        cases_route=LITE_CASES_ROUTE,
        tasks_route=LITE_TASKS_ROUTE,
        verdict_route=LITE_VERDICT_ROUTE,
        aggregate_route=LITE_AGGREGATE_ROUTE,
        benchmark_id=LITE_BENCHMARK_ID,
        benchmark_revision=LITE_REVISION,
        judge_passes=LITE_JUDGE_PASSES,
        criterion_count=LITE_CRITERION_COUNT,
        case_ids=LITE_CASE_IDS,
    )
    _install_protocol(
        node,
        root,
        cases_route=SMOKE_CASES_ROUTE,
        tasks_route=SMOKE_TASKS_ROUTE,
        verdict_route=SMOKE_VERDICT_ROUTE,
        aggregate_route=SMOKE_AGGREGATE_ROUTE,
        benchmark_id=SMOKE_BENCHMARK_ID,
        benchmark_revision=SMOKE_REVISION,
        judge_passes=SMOKE_JUDGE_PASSES,
        criterion_count=SMOKE_CRITERION_COUNT,
        case_ids=(1,),
    )


def _install_protocol(
    node: Url4Node,
    root: Path,
    *,
    cases_route: str,
    tasks_route: str,
    verdict_route: str,
    aggregate_route: str,
    benchmark_id: str,
    benchmark_revision: str,
    judge_passes: int,
    criterion_count: int | None,
    case_ids: tuple[int, ...] | None,
) -> None:
    """Register one DRACO multiplicity profile over the shared pinned assets."""

    node.data(cases_route, _cases(root, case_ids), media_type="application/json")
    node.endpoint(tasks_route)(_task_rows(root))
    node.endpoint(verdict_route)(_criterion_verdict)
    node.endpoint(aggregate_route)(
        _aggregate(
            root,
            benchmark_id,
            benchmark_revision,
            judge_passes,
            criterion_count,
            case_ids,
        )
    )


def _cases(root: Path, case_ids: tuple[int, ...] | None):
    def cases() -> str:
        raw = _read(root / "cases.json", "DRACO cases")
        return json.dumps(_select_cases(raw, case_ids), ensure_ascii=False, separators=(",", ":"))

    return cases


def _task_rows(root: Path):
    def task_rows(request: Request) -> str:
        try:
            case_id = tasks.positive_case_id(request.intent)
            output, finish_reason = decode_candidate_invocation(request.context)
            raw_cases = _read(root / "cases.json", "DRACO cases")
            result = tasks.build_tasks(
                case_id,
                tasks.load_question(root / "criteria", case_id),
                output,
                tasks.load_criteria(root / "criteria", case_id),
            )
            case_record = records.bind_case(
                raw_cases,
                case_id=case_id,
                output=output,
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
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

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
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _aggregate(
    root: Path,
    benchmark_id: str,
    benchmark_revision: str,
    judge_passes: int,
    criterion_count: int | None,
    case_ids: tuple[int, ...] | None,
):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise ResolutionError(
                f"unsupported DRACO operation {request.intent!r}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        try:
            selected_cases = _select_cases(_read(root / "cases.json", "DRACO cases"), case_ids)
            result = scoring.aggregate(
                request.context,
                scoring.load_rubrics(root / "rubrics"),
                benchmark_id,
                selected_cases=selected_cases,
                judge_passes=judge_passes,
                benchmark_revision=benchmark_revision,
                criterion_count=criterion_count,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return aggregate


def _select_cases(raw: str, case_ids: tuple[int, ...] | None) -> list[dict[str, object]]:
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("expected a JSON array of objects")
        if case_ids is None:
            return rows
        by_id = {row["id"]: row for row in rows}
        return [by_id[case_id] for case_id in case_ids]
    except (KeyError, TypeError, ValueError) as exc:
        raise _unavailable(f"could not select DRACO cases {case_ids}: {exc}") from exc


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _unavailable(f"could not read {label} at {str(path)!r}: {exc}") from exc


def _unavailable(detail: str) -> ResolutionError:
    return ResolutionError(
        detail,
        code="benchmark_unavailable",
        permanent=True,
    )


__all__ = ["install"]
