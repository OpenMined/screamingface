"""Install DRACO's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from pathlib import Path

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.draco import aggregate as scoring
from url4_cloud.benchmarks.draco import tasks
from url4_cloud.benchmarks.draco.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASES_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
)
from url4_cloud.benchmarks.draco.verdict import bind, binding_key


def install(node: Url4Node, root: Path) -> None:
    """Register every route referenced by the DRACO expression.

    Providers read lazily so a general-purpose Runner can carry the installed definition without
    requiring DRACO's private image assets until an expression actually selects DRACO.
    """

    node.data(CASES_ROUTE, _cases(root), media_type="application/json")
    node.endpoint(TASKS_ROUTE)(_task_rows(root))
    node.endpoint(VERDICT_ROUTE)(_criterion_verdict)
    node.endpoint(AGGREGATE_ROUTE)(_aggregate(root))


def _cases(root: Path):
    def cases() -> str:
        return _read(root / "cases.json", "DRACO cases")

    return cases


def _task_rows(root: Path):
    def task_rows(request: Request) -> str:
        try:
            case_id = tasks.positive_case_id(request.intent)
            result = tasks.build_tasks(
                case_id,
                tasks.load_question(root / "criteria", case_id),
                request.context,
                tasks.load_criteria(root / "criteria", case_id),
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return task_rows


def _criterion_verdict(request: Request) -> str:
    try:
        case_id, criterion_id = binding_key(request.intent)
        record = bind(request.context, case_id=case_id, criterion_id=criterion_id)
    except ValueError as exc:
        raise _unavailable(str(exc)) from exc
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _aggregate(root: Path):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise ResolutionError(
                f"unsupported DRACO operation {request.intent!r}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        try:
            result = scoring.aggregate(
                request.context,
                scoring.load_rubrics(root / "rubrics"),
                BENCHMARK_ID,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return aggregate


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
