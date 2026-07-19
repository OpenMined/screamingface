"""Strict HTTP client and wire decoders for the ScreamingFace engine profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import httpx

from screamingface._config import current_engine_url
from screamingface._engine_http import unique_json_object
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import (
    EngineConnectionError,
    EngineProfileError,
    EngineProtocolError,
    InvalidBenchmarkError,
    UnknownBenchmarkError,
    UnknownModelError,
)
from screamingface.graders import ExactChoice, Rubric
from screamingface.model_inputs import ParameterValue

REGISTRY_PATH = "/.well-known/screamingface"
REGISTRY_SCHEMA = "screamingface.registry.v1"
BENCHMARK_SCHEMA = "screamingface.benchmark.v1"
FUSION_RESULT_SCHEMA = "screamingface.fusion-result.v1"


@dataclass(frozen=True, slots=True)
class ModelRecord:
    id: str
    supported_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReducerRecord:
    id: str
    route: str


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    id: str
    manifest: str
    tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Registry:
    models: tuple[ModelRecord, ...]
    reducers: tuple[ReducerRecord, ...]
    benchmarks: tuple[BenchmarkRecord, ...]
    response_schemas: tuple[str, ...]


def load_registry() -> Registry:
    payload = _json_object(_get_text(REGISTRY_PATH), "engine registry", EngineProfileError)
    try:
        _exact_fields(
            payload,
            {"schema", "response_schemas", "models", "reducers", "benchmarks"},
            "engine registry",
        )
        if payload["schema"] != REGISTRY_SCHEMA:
            raise ValueError(f"expected schema {REGISTRY_SCHEMA!r}")
        response_schemas = _string_list(payload["response_schemas"], "response_schemas")
        models = tuple(_model_record(item) for item in _object_list(payload["models"], "models"))
        reducers = tuple(
            _reducer_record(item) for item in _object_list(payload["reducers"], "reducers")
        )
        benchmarks = tuple(
            _benchmark_record(item) for item in _object_list(payload["benchmarks"], "benchmarks")
        )
        _unique((record.id for record in models), "model")
        _unique((record.id for record in reducers), "reducer")
        _unique((record.id for record in benchmarks), "benchmark")
        if FUSION_RESULT_SCHEMA not in response_schemas:
            raise ValueError(f"missing response schema {FUSION_RESULT_SCHEMA!r}")
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineProfileError(f"invalid engine registry: {exc}") from exc
    return Registry(models, reducers, benchmarks, response_schemas)


def load_benchmark(benchmark_id: str) -> Benchmark:
    requested = _nonempty(benchmark_id, "benchmark ID")
    registry = load_registry()
    return load_benchmark_from_registry(requested, registry)


def load_benchmark_from_registry(benchmark_id: str, registry: Registry) -> Benchmark:
    """Load one benchmark using an already validated registry snapshot."""

    requested = _nonempty(benchmark_id, "benchmark ID")
    record = next((item for item in registry.benchmarks if item.id == requested), None)
    if record is None:
        raise UnknownBenchmarkError(f"unknown benchmark {requested!r}")
    payload = _json_object(
        _get_text(record.manifest),
        f"benchmark {requested!r} manifest",
        InvalidBenchmarkError,
    )
    return _decode_benchmark(payload, record, registry)


def _decode_benchmark(
    payload: dict[str, object], record: BenchmarkRecord, registry: Registry
) -> Benchmark:
    label = f"benchmark {record.id!r}"
    try:
        _exact_fields(
            payload,
            {"schema", "id", "title", "tools", "cases", "grader", "aggregator"},
            label,
        )
        if payload["schema"] != BENCHMARK_SCHEMA:
            raise ValueError(f"expected schema {BENCHMARK_SCHEMA!r}")
        if payload["id"] != record.id:
            raise ValueError("manifest ID does not match registry ID")
        title = _nonempty(payload["title"], "benchmark title")
        tools = _string_list(payload["tools"], "benchmark tools")
        if tools != record.tools:
            raise ValueError("manifest tools do not match registry tools")
        cases_config = _required_object(payload["cases"], "cases")
        _exact_fields(cases_config, {"url", "format"}, "benchmark cases")
        cases_url = _relative_path(cases_config["url"], "benchmark cases URL")
        if cases_config["format"] != "ndjson":
            raise ValueError("benchmark cases format must be 'ndjson'")
        grader = _decode_grader(_required_object(payload["grader"], "grader"), registry)
        aggregator = _decode_aggregator(_required_object(payload["aggregator"], "aggregator"))
        cases = _decode_cases(_get_text(cases_url), grader, record.id)
        return Benchmark(
            record.id,
            title=title,
            cases=cases,
            grader=grader,
            aggregator=aggregator,
            tools=tools,
        )
    except UnknownModelError:
        raise
    except InvalidBenchmarkError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidBenchmarkError(f"invalid {label}: {exc}") from exc


def _decode_grader(payload: dict[str, object], registry: Registry) -> ExactChoice | Rubric:
    kind = payload.get("type")
    if kind == "exact_choice":
        _exact_fields(payload, {"type"}, "exact-choice grader")
        return ExactChoice()
    if kind != "rubric":
        raise ValueError(f"unknown grader type {kind!r}")
    _exact_fields(payload, {"type", "model", "prompt", "passes", "params"}, "rubric grader")
    model = _nonempty(payload["model"], "rubric model")
    if model not in {record.id for record in registry.models}:
        raise UnknownModelError(f"unknown rubric judge model {model!r}")
    passes = payload["passes"]
    if isinstance(passes, bool) or not isinstance(passes, int):
        raise TypeError("rubric passes must be an integer")
    params = _parameter_map(payload["params"])
    return Rubric(
        model=model,
        prompt=_nonempty(payload["prompt"], "rubric prompt"),
        passes=passes,
        params=params,
    )


def _decode_aggregator(payload: dict[str, object]) -> Mean:
    _exact_fields(payload, {"type"}, "aggregator")
    if payload.get("type") != "mean":
        raise ValueError(f"unknown aggregator type {payload.get('type')!r}")
    return Mean()


def _decode_cases(body: str, grader: ExactChoice | Rubric, benchmark_id: str) -> tuple[Case, ...]:
    cases: list[Case] = []
    seen: set[str] = set()
    for line_number, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        payload = _json_object(
            line,
            f"benchmark {benchmark_id!r} case line {line_number}",
            InvalidBenchmarkError,
        )
        try:
            _exact_fields(payload, {"id", "input", "reference", "metadata"}, "benchmark case")
            case = Case(
                _nonempty(payload["id"], "case ID"),
                _nonempty(payload["input"], "case input"),
                reference=payload["reference"],
                metadata=_required_object(payload["metadata"], "case metadata"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidBenchmarkError(
                f"invalid benchmark {benchmark_id!r} case line {line_number}: {exc}"
            ) from exc
        if case.id in seen:
            raise InvalidBenchmarkError(f"duplicate case ID: {case.id}")
        if case.reference is None:
            raise InvalidBenchmarkError(f"case {case.id!r} has no reference for {grader.kind}")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise InvalidBenchmarkError(f"benchmark {benchmark_id!r} has no cases")
    return tuple(cases)


def _get_text(path: str) -> str:
    route = _relative_path(path, "engine profile path")
    base_url = current_engine_url()
    try:
        response = httpx.get(f"{base_url}{route}", timeout=30.0)
    except httpx.HTTPError as exc:
        raise EngineConnectionError(f"could not reach URL4 engine at {base_url}: {exc}") from exc
    if not response.is_success:
        raise EngineProtocolError(f"URL4 engine returned HTTP {response.status_code} for {route}")
    return response.text


def _json_object(
    body: str, label: str, error_type: type[EngineProfileError] | type[InvalidBenchmarkError]
) -> dict[str, object]:
    try:
        return unique_json_object(body)
    except (TypeError, ValueError) as exc:
        raise error_type(f"invalid {label}: {exc}") from exc


def _model_record(payload: dict[str, object]) -> ModelRecord:
    _exact_fields(payload, {"id", "supported_tools"}, "model record")
    return ModelRecord(
        _nonempty(payload["id"], "model ID"),
        _string_list(payload["supported_tools"], "model supported_tools"),
    )


def _reducer_record(payload: dict[str, object]) -> ReducerRecord:
    _exact_fields(payload, {"id", "route"}, "reducer record")
    return ReducerRecord(
        _nonempty(payload["id"], "reducer ID"),
        _relative_path(payload["route"], "reducer route"),
    )


def _benchmark_record(payload: dict[str, object]) -> BenchmarkRecord:
    _exact_fields(payload, {"id", "manifest", "tools"}, "benchmark record")
    return BenchmarkRecord(
        _nonempty(payload["id"], "benchmark ID"),
        _relative_path(payload["manifest"], "benchmark manifest"),
        _string_list(payload["tools"], "benchmark tools"),
    )


def _exact_fields(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise ValueError(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def _object_list(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(f"{label} must be a list of objects")
    return value


def _required_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _parameter_map(value: object) -> dict[str, ParameterValue]:
    payload = _required_object(value, "rubric params")
    for key, item in payload.items():
        if not isinstance(key, str) or not isinstance(item, (str, int, float, bool)):
            raise TypeError("rubric params must contain JSON scalar values")
    return cast("dict[str, ParameterValue]", payload)


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result = tuple(_nonempty(item, label) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _relative_path(value: object, label: str) -> str:
    path = _nonempty(value, label)
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise ValueError(f"{label} must be a same-engine absolute path")
    return path


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _unique(values: Any, label: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {label} ID")
