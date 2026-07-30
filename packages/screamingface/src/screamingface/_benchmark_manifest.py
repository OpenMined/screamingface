"""Decode the Engine-owned metadata needed to compile one Benchmark evaluation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, cast

import httpx
import yaml

from screamingface.discovery import BenchmarkInfo, ScoreDirection
from screamingface.errors import PlanningError


@dataclass(frozen=True, slots=True)
class _BenchmarkManifest:
    info: BenchmarkInfo
    cases_route: str
    grader_route: str
    aggregator_route: str
    criteria_per_case: int
    required_capabilities: tuple[str, ...]


def load_manifest(http: httpx.Client, benchmark: str) -> _BenchmarkManifest:
    """Resolve one Engine-owned Benchmark manifest and verify its advertised digest."""

    try:
        catalog_response = http.get("/v1/benchmarks")
        manifest_response = http.get(f"/v1/benchmarks/{benchmark}/manifest")
    except httpx.HTTPError as exc:
        raise PlanningError(
            "Could not reach the SF Engine Benchmark catalog",
            code="engine_unreachable",
            permanent=False,
        ) from exc
    _success(catalog_response, "list Benchmarks")
    _success(manifest_response, f"load Benchmark {benchmark!r}")

    return _verified_manifest(catalog_response, manifest_response, benchmark)


async def load_manifest_async(
    http: httpx.AsyncClient,
    benchmark: str,
) -> _BenchmarkManifest:
    """Resolve and verify one Engine-owned Benchmark manifest asynchronously."""

    try:
        catalog_response = await http.get("/v1/benchmarks")
        manifest_response = await http.get(f"/v1/benchmarks/{benchmark}/manifest")
    except httpx.HTTPError as exc:
        raise PlanningError(
            "Could not reach the SF Engine Benchmark catalog",
            code="engine_unreachable",
            permanent=False,
        ) from exc
    _success(catalog_response, "list Benchmarks")
    _success(manifest_response, f"load Benchmark {benchmark!r}")
    return _verified_manifest(catalog_response, manifest_response, benchmark)


def _verified_manifest(
    catalog_response: httpx.Response,
    manifest_response: httpx.Response,
    benchmark: str,
) -> _BenchmarkManifest:
    record = _catalog_record(catalog_response, benchmark)
    raw = manifest_response.content
    actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    expected_digest = _text(record.get("manifest_digest"), "manifest digest")
    if actual_digest != expected_digest:
        raise PlanningError(
            "SF Engine Benchmark manifest does not match its advertised digest",
            code="manifest_digest_mismatch",
            permanent=True,
        )
    try:
        decoded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PlanningError(
            "SF Engine Benchmark manifest is not valid YAML",
            code="invalid_benchmark_manifest",
            permanent=True,
        ) from exc
    return _decode_manifest(decoded, actual_digest)


def _decode_manifest(decoded: object, digest: str) -> _BenchmarkManifest:
    manifest = _mapping(decoded, "Benchmark manifest")
    if manifest.get("schema") != "screamingface.benchmark-manifest.v1":
        raise PlanningError(
            "SF Engine returned an unsupported Benchmark manifest schema",
            code="unsupported_benchmark_manifest",
            permanent=True,
        )

    cases = _mapping(manifest.get("cases"), "manifest cases")
    grader = _mapping(manifest.get("grader"), "manifest grader")
    aggregator = _mapping(manifest.get("aggregator"), "manifest aggregator")
    metrics = _mapping(manifest.get("metrics"), "manifest metrics")
    tools = manifest.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools):
        _invalid("manifest tools must be an array of names")
    selected_tools = cast(list[str], tools)
    info = BenchmarkInfo(
        name=_text(manifest.get("name"), "Benchmark name"),
        id=_text(manifest.get("id"), "Benchmark id"),
        manifest_digest=digest,
        title=_text(manifest.get("title"), "Benchmark title"),
        case_count=_positive(cases.get("count"), "Benchmark case count"),
        primary_metric=_text(metrics.get("primary"), "primary metric"),
        score_direction=_direction(metrics.get("direction")),
    )
    return _BenchmarkManifest(
        info=info,
        cases_route=_route(cases.get("route"), "cases route"),
        grader_route=_route(grader.get("route"), "grader route"),
        aggregator_route=_route(aggregator.get("route"), "aggregator route"),
        criteria_per_case=_positive(grader.get("criteria_per_case"), "criteria per case"),
        required_capabilities=tuple(selected_tools),
    )


def _catalog_record(response: httpx.Response, benchmark: str) -> Mapping[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise PlanningError(
            "SF Engine Benchmark catalog must be JSON",
            code="invalid_benchmark_catalog",
            permanent=True,
        ) from exc
    values = _mapping(payload, "Benchmark catalog").get("benchmarks")
    if not isinstance(values, list):
        _invalid("Benchmark catalog must contain a benchmarks array")
    for value in cast(list[object], values):
        record = _mapping(value, "Benchmark catalog record")
        if benchmark in {record.get("name"), record.get("id")}:
            return record
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


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} must be non-blank text")
    return cast(str, value).strip()


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid(f"{label} must be a positive integer")
    return cast(int, value)


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
