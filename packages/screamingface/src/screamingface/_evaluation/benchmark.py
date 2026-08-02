"""Decode one Engine-owned Benchmark expression resource."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, cast

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface._evaluation.model import _canonical_url4
from screamingface.discovery import BenchmarkInfo
from screamingface.errors import PlanningError

_SCHEMA = "screamingface.benchmark.v1"


@dataclass(frozen=True, slots=True)
class _BenchmarkResource:
    info: BenchmarkInfo
    case_count: int
    url4: str
    required_models: tuple[str, ...]


def _decode_benchmark_resource(
    decoded: object,
    *,
    requested_id: str | None,
    requested_limit: int | None,
) -> _BenchmarkResource:
    resource = _wire_mapping(decoded, "Benchmark resource", _invalid)
    if resource.get("schema") != _SCHEMA:
        _invalid(f"Benchmark resource schema must be {_SCHEMA!r}")
    benchmark_id = _wire_text(resource.get("id"), "Benchmark id", _invalid)
    if requested_id not in {None, "default", benchmark_id}:
        _invalid("Benchmark resource has the wrong Benchmark id")
    total_case_count = _positive(resource.get("total_case_count"), "total_case_count")
    case_count = _positive(resource.get("case_count"), "case_count")
    expected_count = (
        total_case_count if requested_limit is None else min(requested_limit, total_case_count)
    )
    if case_count != expected_count:
        _invalid("Benchmark resource case_count does not match the requested limit")

    try:
        url4 = _canonical_url4(resource.get("url4"), "Benchmark")
        info = BenchmarkInfo(
            id=benchmark_id,
            revision=_wire_text(resource.get("revision"), "Benchmark revision", _invalid),
            case_count=total_case_count,
        )
    except (TypeError, ValueError) as exc:
        _invalid(str(exc))

    return _BenchmarkResource(
        info=info,
        case_count=case_count,
        url4=url4,
        required_models=_names(resource.get("required_models"), "required models"),
    )


def _names(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        _invalid(f"Benchmark resource {label} must be an array")
    selected = tuple(_wire_text(item, label, _invalid) for item in value)
    if len(selected) != len(set(selected)):
        _invalid(f"Benchmark resource {label} must be unique")
    return selected


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid(f"Benchmark resource {label} must be a positive integer")
    return cast(int, value)


def _invalid(message: str) -> NoReturn:
    raise PlanningError(
        message,
        code="invalid_benchmark_resource",
        permanent=True,
    )


__all__: list[str] = []
