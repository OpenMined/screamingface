"""Decode the Engine-owned metadata needed to compile one Benchmark evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, cast

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface.discovery import BenchmarkInfo, ScoreDirection
from screamingface.errors import PlanningError


@dataclass(frozen=True, slots=True)
class _BenchmarkManifest:
    info: BenchmarkInfo
    cases_route: str
    criteria_route: str
    aggregate_route: str
    answer_instructions: str
    answer_params: tuple[tuple[str, str], ...]
    synthesis_model: str
    synthesis_instructions: str
    synthesis_params: tuple[tuple[str, str], ...]
    judge_model: str
    judge_instructions: str
    judge_passes: int
    judge_params: tuple[tuple[str, str], ...]
    criteria_per_case: int
    required_capabilities: tuple[str, ...]


def _decode_manifest(decoded: object) -> _BenchmarkManifest:
    manifest = _wire_mapping(decoded, "Benchmark manifest", _invalid)
    cases = _wire_mapping(manifest.get("cases"), "manifest cases", _invalid)
    answer = _wire_mapping(manifest.get("answer"), "manifest answer", _invalid)
    synthesis = _wire_mapping(manifest.get("synthesis"), "manifest synthesis", _invalid)
    grader = _wire_mapping(manifest.get("grader"), "manifest grader", _invalid)
    aggregator = _wire_mapping(manifest.get("aggregator"), "manifest aggregator", _invalid)
    metrics = _wire_mapping(manifest.get("metrics"), "manifest metrics", _invalid)
    if grader.get("kind") != "rubric":
        _invalid("manifest grader kind must be 'rubric'")
    if aggregator.get("kind") != "mean":
        _invalid("manifest aggregator kind must be 'mean'")
    tools = manifest.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools):
        _invalid("manifest tools must be an array of names")
    selected_tools = cast(list[str], tools)
    benchmark_id = _wire_text(manifest.get("id"), "Benchmark id", _invalid)
    info = BenchmarkInfo(
        name=benchmark_id,
        id=benchmark_id,
        title=_wire_text(manifest.get("title"), "Benchmark title", _invalid),
        case_count=_positive(cases.get("count"), "Benchmark case count"),
        primary_metric=_wire_text(metrics.get("primary"), "primary metric", _invalid),
        score_direction=_direction(metrics.get("direction")),
    )
    return _BenchmarkManifest(
        info=info,
        cases_route=_route(cases.get("route"), "Benchmark cases route"),
        criteria_route=_criteria_route(
            grader.get("criteria_route"),
            "Benchmark criteria route",
        ),
        aggregate_route=_route(aggregator.get("route"), "Benchmark aggregate route"),
        answer_instructions=_wire_text(answer.get("instructions"), "answer instructions", _invalid),
        answer_params=_params(answer.get("params"), "answer params"),
        synthesis_model=_wire_text(synthesis.get("model"), "synthesis model", _invalid),
        synthesis_instructions=_wire_text(
            synthesis.get("instructions"), "synthesis instructions", _invalid
        ),
        synthesis_params=_params(synthesis.get("params"), "synthesis params"),
        judge_model=_wire_text(grader.get("model"), "judge model", _invalid),
        judge_instructions=_wire_text(grader.get("instructions"), "judge instructions", _invalid),
        judge_passes=_positive(grader.get("passes"), "judge passes"),
        judge_params=_params(grader.get("params"), "judge params"),
        criteria_per_case=_positive(grader.get("criteria_per_case"), "criteria per case"),
        required_capabilities=tuple(selected_tools),
    )


def _route(value: object, label: str) -> str:
    route = _wire_text(value, label, _invalid)
    if not route.startswith("/"):
        _invalid(f"{label} must begin with '/'")
    return route


def _criteria_route(value: object, label: str) -> str:
    route = _route(value, label)
    if route.count("{case_id}") != 1:
        _invalid(f"{label} must contain exactly one '{{case_id}}' placeholder")
    return route


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid(f"{label} must be a positive integer")
    return cast(int, value)


def _params(value: object, label: str) -> tuple[tuple[str, str], ...]:
    raw = _wire_mapping(value, label, _invalid)
    result: list[tuple[str, str]] = []
    for name, item in raw.items():
        if not isinstance(name, str) or not name.strip():
            _invalid(f"{label} names must be non-blank text")
        if isinstance(item, bool):
            selected = "true" if item else "false"
        elif isinstance(item, str | int | float):
            selected = str(item)
        else:
            _invalid(f"{label} value {name!r} must be a scalar")
        result.append((name, selected))
    return tuple(result)


def _direction(value: object) -> ScoreDirection:
    if value not in {"maximize", "minimize"}:
        _invalid("metric direction must be maximize or minimize")
    return cast(ScoreDirection, value)


def _invalid(message: str) -> NoReturn:
    raise PlanningError(
        message,
        code="invalid_benchmark_manifest",
        permanent=True,
    )


__all__: list[str] = []
