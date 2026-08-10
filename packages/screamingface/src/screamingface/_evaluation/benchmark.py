"""Decode one flat Engine-owned Benchmark expression resource."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, cast

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface._evaluation.model import _canonical_url4
from screamingface.discovery import BenchmarkInfo
from screamingface.errors import PlanningError

_BENCHMARK_SCHEMA = "screamingface.benchmark.v1"


@dataclass(frozen=True, slots=True)
class _BenchmarkResource:
    info: BenchmarkInfo
    case_count: int
    url4: str


def _decode_benchmark_resource(
    decoded: object,
    *,
    requested_id: str,
    requested_limit: int | None,
) -> _BenchmarkResource:
    """Validate the one executable resource selected by its complete Benchmark id."""

    resource = _wire_mapping(decoded, "Benchmark resource", _invalid)
    if resource.get("schema") != _BENCHMARK_SCHEMA:
        _invalid(f"Benchmark resource schema must be {_BENCHMARK_SCHEMA!r}")
    benchmark_id = _wire_text(resource.get("id"), "Benchmark id", _invalid)
    if benchmark_id != requested_id:
        _invalid("Benchmark resource has the wrong Benchmark id")
    for field in ("variant", "title", "description"):
        _wire_text(resource.get(field), f"Benchmark {field}", _invalid)
    installed_case_count = _positive(resource.get("case_count"), "case_count")
    try:
        url4 = _canonical_url4(resource.get("url4"), "Benchmark")
        info = BenchmarkInfo(
            id=benchmark_id,
            revision=_wire_text(resource.get("revision"), "Benchmark revision", _invalid),
            case_count=installed_case_count,
        )
    except (TypeError, ValueError) as exc:
        _invalid(str(exc))

    return _BenchmarkResource(
        info=info,
        case_count=(
            installed_case_count
            if requested_limit is None
            else min(requested_limit, installed_case_count)
        ),
        url4=url4,
    )


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
