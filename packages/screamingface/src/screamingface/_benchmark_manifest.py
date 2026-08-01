"""Decode the Engine-owned metadata needed to compile one Benchmark evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, cast

import httpx
import yaml

from screamingface._benchmark_catalog import _decode_benchmark_catalog
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


def load_manifest(http: httpx.Client, benchmark: str | None = None) -> _BenchmarkManifest:
    """Resolve one catalogued Engine-owned Benchmark manifest."""

    try:
        catalog_response = http.get("/v1/benchmarks")
    except httpx.HTTPError as exc:
        raise PlanningError(
            "Could not reach the SF Engine Benchmark catalog",
            code="engine_unreachable",
            permanent=False,
        ) from exc
    _success(catalog_response, "list Benchmarks")
    selected = _select_benchmark(catalog_response, benchmark)

    try:
        manifest_response = http.get(f"/v1/benchmarks/{selected}")
    except httpx.HTTPError as exc:
        raise PlanningError(
            f"Could not reach SF Engine Benchmark {selected!r}",
            code="engine_unreachable",
            permanent=False,
        ) from exc
    _success(manifest_response, f"load Benchmark {selected!r}")
    return _verified_manifest(manifest_response)


async def load_manifest_async(
    http: httpx.AsyncClient,
    benchmark: str | None = None,
) -> _BenchmarkManifest:
    """Resolve one catalogued Engine-owned Benchmark manifest asynchronously."""

    try:
        catalog_response = await http.get("/v1/benchmarks")
    except httpx.HTTPError as exc:
        raise PlanningError(
            "Could not reach the SF Engine Benchmark catalog",
            code="engine_unreachable",
            permanent=False,
        ) from exc
    _success(catalog_response, "list Benchmarks")
    selected = _select_benchmark(catalog_response, benchmark)

    try:
        manifest_response = await http.get(f"/v1/benchmarks/{selected}")
    except httpx.HTTPError as exc:
        raise PlanningError(
            f"Could not reach SF Engine Benchmark {selected!r}",
            code="engine_unreachable",
            permanent=False,
        ) from exc
    _success(manifest_response, f"load Benchmark {selected!r}")
    return _verified_manifest(manifest_response)


def _verified_manifest(manifest_response: httpx.Response) -> _BenchmarkManifest:
    raw = manifest_response.content
    try:
        decoded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PlanningError(
            "SF Engine Benchmark manifest is not valid YAML",
            code="invalid_benchmark_manifest",
            permanent=True,
        ) from exc
    return _decode_manifest(decoded)


def _decode_manifest(decoded: object) -> _BenchmarkManifest:
    manifest = _mapping(decoded, "Benchmark manifest")
    cases = _mapping(manifest.get("cases"), "manifest cases")
    answer = _mapping(manifest.get("answer"), "manifest answer")
    synthesis = _mapping(manifest.get("synthesis"), "manifest synthesis")
    grader = _mapping(manifest.get("grader"), "manifest grader")
    aggregator = _mapping(manifest.get("aggregator"), "manifest aggregator")
    metrics = _mapping(manifest.get("metrics"), "manifest metrics")
    if grader.get("kind") != "rubric":
        _invalid("manifest grader kind must be 'rubric'")
    if aggregator.get("kind") != "mean":
        _invalid("manifest aggregator kind must be 'mean'")
    tools = manifest.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools):
        _invalid("manifest tools must be an array of names")
    selected_tools = cast(list[str], tools)
    benchmark_id = _text(manifest.get("id"), "Benchmark id")
    info = BenchmarkInfo(
        name=benchmark_id,
        id=benchmark_id,
        title=_text(manifest.get("title"), "Benchmark title"),
        case_count=_positive(cases.get("count"), "Benchmark case count"),
        primary_metric=_text(metrics.get("primary"), "primary metric"),
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
        answer_instructions=_text(answer.get("instructions"), "answer instructions"),
        answer_params=_params(answer.get("params"), "answer params"),
        synthesis_model=_text(synthesis.get("model"), "synthesis model"),
        synthesis_instructions=_text(synthesis.get("instructions"), "synthesis instructions"),
        synthesis_params=_params(synthesis.get("params"), "synthesis params"),
        judge_model=_text(grader.get("model"), "judge model"),
        judge_instructions=_text(grader.get("instructions"), "judge instructions"),
        judge_passes=_positive(grader.get("passes"), "judge passes"),
        judge_params=_params(grader.get("params"), "judge params"),
        criteria_per_case=_positive(grader.get("criteria_per_case"), "criteria per case"),
        required_capabilities=tuple(selected_tools),
    )


def _select_benchmark(response: httpx.Response, benchmark: str | None) -> str:
    try:
        payload = response.json()
    except ValueError as exc:
        raise PlanningError(
            "SF Engine Benchmark catalog must be JSON",
            code="invalid_benchmark_catalog",
            permanent=True,
        ) from exc
    try:
        catalog = _decode_benchmark_catalog(payload)
    except ValueError as exc:
        raise PlanningError(
            str(exc),
            code="invalid_benchmark_catalog",
            permanent=True,
        ) from exc
    if benchmark is None:
        if catalog.default is None:
            raise PlanningError(
                "SF Engine exposes no Benchmarks",
                code="no_benchmarks",
                permanent=True,
            )
        return catalog.default
    if benchmark in catalog.ids:
        return benchmark
    raise PlanningError(
        f"SF Engine does not expose Benchmark {benchmark!r}",
        code="unknown_benchmark",
        permanent=True,
    )


def _success(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    raise PlanningError(
        f"Could not {operation}: HTTP {response.status_code}",
        code="engine_contract_error",
        permanent=response.status_code < 500,
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _route(value: object, label: str) -> str:
    route = _text(value, label)
    if not route.startswith("/"):
        _invalid(f"{label} must begin with '/'")
    return route


def _criteria_route(value: object, label: str) -> str:
    route = _route(value, label)
    if route.count("{case_id}") != 1:
        _invalid(f"{label} must contain exactly one '{{case_id}}' placeholder")
    return route


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} must be non-blank text")
    return cast(str, value).strip()


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid(f"{label} must be a positive integer")
    return cast(int, value)


def _params(value: object, label: str) -> tuple[tuple[str, str], ...]:
    raw = _mapping(value, label)
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
