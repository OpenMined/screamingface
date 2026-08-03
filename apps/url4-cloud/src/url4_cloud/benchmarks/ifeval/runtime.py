"""Install IFEval's private assets and deterministic functions into one Runner world."""

from __future__ import annotations

import json
from pathlib import Path

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.ifeval import aggregate as scoring
from url4_cloud.benchmarks.ifeval import grading
from url4_cloud.benchmarks.ifeval.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASES_ROUTE,
    CHECK_ROUTE,
)


def install(node: Url4Node, root: Path) -> None:
    """Register every route referenced by the IFEval expression.

    Providers read lazily so a general-purpose Runner can carry the installed definition
    without requiring IFEval's private assets until an expression actually selects it.
    """

    node.data(CASES_ROUTE, _cases(root), media_type="application/json")
    node.endpoint(CHECK_ROUTE)(_check(root))
    node.endpoint(AGGREGATE_ROUTE)(_aggregate(root))


def _cases(root: Path):
    def cases() -> str:
        return _read(root / "cases.json", "IFEval cases")

    return cases


def _check(root: Path):
    def check(request: Request) -> str:
        try:
            case_id = _positive_case_id(request.intent)
            spec = json.loads(
                _read(root / "instructions" / f"{case_id}.json", f"IFEval case {case_id} spec")
            )
            grading.configure_nltk(root / "nltk_data")
            result = grading.check_case(
                instruction_id_list=spec["instruction_id_list"],
                kwargs_list=spec["kwargs"],
                prompt=spec["prompt"],
                response=request.context,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        record = {
            "schema": scoring.SCHEMA,
            "case_id": case_id,
            "valid": True,
            "instruction_id_list": spec["instruction_id_list"],
            "strict": result["strict"],
            "loose": result["loose"],
        }
        return json.dumps(record, ensure_ascii=False, separators=(",", ":"))

    return check


def _aggregate(root: Path):
    def aggregate(request: Request) -> str:
        if request.intent != "aggregate":
            raise ResolutionError(
                f"unsupported IFEval operation {request.intent!r}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        try:
            result = scoring.aggregate(
                request.context,
                scoring.load_specs(root / "instructions"),
                BENCHMARK_ID,
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return aggregate


def _positive_case_id(value: str) -> int:
    try:
        case_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"IFEval check intent must be a case id, got {value!r}") from None
    if case_id < 1:
        raise ValueError(f"IFEval case id must be positive, got {case_id}")
    return case_id


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
