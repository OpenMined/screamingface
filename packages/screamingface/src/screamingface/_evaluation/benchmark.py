"""Decode one Engine-owned Benchmark expression resource."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, cast

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface._evaluation.model import _canonical_url4
from screamingface.discovery import BenchmarkInfo
from screamingface.errors import PlanningError

_FAMILY_SCHEMA = "screamingface.benchmark-family.v1"
_BENCHMARK_SCHEMA = "screamingface.benchmark.v1"


@dataclass(frozen=True, slots=True)
class _BenchmarkResource:
    info: BenchmarkInfo
    case_count: int
    url4: str
    required_models: tuple[str, ...]


def _decode_benchmark_resource(
    decoded: object,
    *,
    requested_id: str,
    requested_limit: int | None,
) -> _BenchmarkResource:
    resource = _wire_mapping(decoded, "Benchmark resource", _invalid)
    schema = resource.get("schema")
    if schema == _FAMILY_SCHEMA:
        return _decode_family_resource(
            resource,
            requested_id=requested_id,
            requested_limit=requested_limit,
        )
    if schema == _BENCHMARK_SCHEMA:
        return _decode_legacy_resource(
            resource,
            requested_id=requested_id,
            requested_limit=requested_limit,
        )
    _invalid(f"Benchmark resource schema must be {_FAMILY_SCHEMA!r} or {_BENCHMARK_SCHEMA!r}")


def _decode_family_resource(
    family: Mapping[str, object],
    *,
    requested_id: str,
    requested_limit: int | None,
) -> _BenchmarkResource:
    requested_family, requested_variant = _selection(requested_id)
    family_id = _wire_text(family.get("id"), "Benchmark Family id", _invalid)
    if requested_family != family_id:
        _invalid("Benchmark resource has the wrong Benchmark Family id")
    default_variant = _wire_text(
        family.get("default_variant"), "Benchmark default Variant", _invalid
    )
    variants = _wire_mapping(family.get("variants"), "Benchmark Variants", _invalid)
    selected_variant = requested_variant or default_variant
    if selected_variant not in variants:
        _invalid(f"Benchmark Variant {selected_variant!r} is not installed in {family_id!r}")
    resource = _wire_mapping(
        variants[selected_variant], f"Benchmark Variant {selected_variant!r}", _invalid
    )
    total_case_count = _positive(resource.get("total_case_count"), "total_case_count")
    case_count = _positive(resource.get("case_count"), "case_count")
    expected_count = (
        total_case_count if requested_limit is None else min(requested_limit, total_case_count)
    )
    if case_count != expected_count:
        _invalid("Benchmark resource case_count does not match the requested limit")

    try:
        url4 = _canonical_url4(resource.get("url4"), "Benchmark")
        benchmark_id = (
            family_id if selected_variant == default_variant else f"{family_id}/{selected_variant}"
        )
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


def _decode_legacy_resource(
    resource: Mapping[str, object],
    *,
    requested_id: str,
    requested_limit: int | None,
) -> _BenchmarkResource:
    """Read the pre-family resource during a rolling Engine/SDK deployment."""

    benchmark_id = _wire_text(resource.get("id"), "Benchmark id", _invalid)
    if benchmark_id != requested_id:
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


def _selection(value: str) -> tuple[str, str | None]:
    if not isinstance(value, str):
        _invalid("Benchmark selection must be text")
    parts = value.split("/")
    if len(parts) > 2 or any(not part.strip() for part in parts):
        _invalid("Benchmark selection must be 'family' or 'family/variant'")
    return parts[0], parts[1] if len(parts) == 2 else None


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
