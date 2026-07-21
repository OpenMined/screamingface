"""Strict HTTP decoder for executable capabilities advertised by the URL4 engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

import httpx

from screamingface._config import current_engine_url
from screamingface._engine_http import unique_json_object
from screamingface._tooling import tool_ids
from screamingface.errors import EngineConnectionError, EngineProfileError, EngineProtocolError
from screamingface.model_inputs import ParameterValue

REGISTRY_PATH = "/.well-known/screamingface"
REGISTRY_SCHEMA = "screamingface.registry.v1"
RECIPE_RESULT_SCHEMA = "screamingface.recipe-result.v1"
CASE_GRADE_SCHEMA = "screamingface.case-grade.v1"
REPORT_SCHEMA = "screamingface.report.v1"
type AuthMethod = Literal["oauth", "api_key"]


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    id: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]


@dataclass(frozen=True, slots=True)
class ModelRecord:
    id: str
    supported_tools: tuple[str, ...]
    provider: str
    required_connections: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReducerRecord:
    id: str
    route: str


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    kind: str
    route: str
    model: str | None = None
    prompt: str | None = None
    passes: int | None = None
    parameter_items: tuple[tuple[str, ParameterValue], ...] = ()

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self.parameter_items)


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    id: str
    title: str
    cases_route: str
    grader: StrategyRecord
    aggregator: StrategyRecord
    tools: tuple[str, ...]
    max_tool_calls: int | None
    tool_policy_route: str | None


@dataclass(frozen=True, slots=True)
class Registry:
    models: tuple[ModelRecord, ...]
    reducers: tuple[ReducerRecord, ...]
    response_schemas: tuple[str, ...]
    max_request_target_bytes: int
    providers: tuple[ProviderRecord, ...]
    benchmarks: tuple[BenchmarkRecord, ...] = ()


def load_registry() -> Registry:
    payload = _json_object(_get_text(REGISTRY_PATH), "engine registry")
    try:
        _exact_fields(
            payload,
            {
                "schema",
                "response_schemas",
                "limits",
                "providers",
                "models",
                "benchmarks",
                "reducers",
            },
            "engine registry",
        )
        if payload["schema"] != REGISTRY_SCHEMA:
            raise ValueError(f"expected schema {REGISTRY_SCHEMA!r}")
        response_schemas = _string_list(payload["response_schemas"], "response_schemas")
        providers = tuple(
            _provider_record(item) for item in _object_list(payload["providers"], "providers")
        )
        models = tuple(_model_record(item) for item in _object_list(payload["models"], "models"))
        benchmarks = tuple(
            _benchmark_record(item) for item in _object_list(payload["benchmarks"], "benchmarks")
        )
        reducers = tuple(
            _reducer_record(item) for item in _object_list(payload["reducers"], "reducers")
        )
        limits = _limits(payload["limits"])
        _unique((record.id for record in models), "model")
        _unique((record.id for record in benchmarks), "benchmark")
        _unique((record.id for record in providers), "provider")
        _unique((record.id for record in reducers), "reducer")
        provider_ids = {record.id for record in providers}
        for model in models:
            _validate_model_connections(model, provider_ids)
        if RECIPE_RESULT_SCHEMA not in response_schemas:
            raise ValueError(f"missing response schema {RECIPE_RESULT_SCHEMA!r}")
        if REPORT_SCHEMA not in response_schemas:
            raise ValueError(f"missing response schema {REPORT_SCHEMA!r}")
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineProfileError(f"invalid engine registry: {exc}") from exc
    return Registry(models, reducers, response_schemas, limits, providers, benchmarks)


def _validate_model_connections(model: ModelRecord, provider_ids: set[str]) -> None:
    if model.provider not in provider_ids:
        raise ValueError(f"model {model.id!r} references unknown provider {model.provider!r}")
    unknown = set(model.required_connections) - provider_ids
    if unknown:
        raise ValueError(
            f"model {model.id!r} references unknown required connection {sorted(unknown)[0]!r}"
        )


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


def _json_object(body: str, label: str) -> dict[str, object]:
    try:
        return unique_json_object(body)
    except (TypeError, ValueError) as exc:
        raise EngineProfileError(f"invalid {label}: {exc}") from exc


def _model_record(payload: dict[str, object]) -> ModelRecord:
    _exact_fields(
        payload,
        {"id", "provider", "supported_tools", "required_connections"},
        "model record",
    )
    return ModelRecord(
        _nonempty(payload["id"], "model ID"),
        tool_ids(
            _string_list(payload["supported_tools"], "model supported_tools"),
            label="model supported_tools",
        ),
        _public_id(payload["provider"], "model provider"),
        tuple(
            _public_id(value, "model required connection")
            for value in _string_list(payload["required_connections"], "model required_connections")
        ),
    )


def _provider_record(payload: dict[str, object]) -> ProviderRecord:
    _exact_fields(payload, {"id", "display_name", "auth_methods"}, "provider record")
    methods = _string_list(payload["auth_methods"], "provider auth_methods")
    invalid = set(methods) - {"oauth", "api_key"}
    if invalid:
        raise ValueError(f"unsupported provider auth method: {sorted(invalid)[0]}")
    if not methods:
        raise ValueError("provider auth_methods must not be empty")
    return ProviderRecord(
        _public_id(payload["id"], "provider ID"),
        _nonempty(payload["display_name"], "provider display_name"),
        cast(tuple[AuthMethod, ...], tuple(methods)),
    )


def _reducer_record(payload: dict[str, object]) -> ReducerRecord:
    _exact_fields(payload, {"id", "route"}, "reducer record")
    return ReducerRecord(
        _nonempty(payload["id"], "reducer ID"),
        _relative_path(payload["route"], "reducer route"),
    )


def _benchmark_record(payload: dict[str, object]) -> BenchmarkRecord:
    _exact_fields(
        payload,
        {
            "id",
            "title",
            "cases_route",
            "grader",
            "aggregator",
            "tools",
            "max_tool_calls",
            "tool_policy_route",
        },
        "benchmark record",
    )
    tools = tool_ids(
        _string_list(payload["tools"], "benchmark tools"),
        label="benchmark tools",
    )
    max_tool_calls = payload["max_tool_calls"]
    raw_tool_policy_route = payload["tool_policy_route"]
    if tools:
        if (
            isinstance(max_tool_calls, bool)
            or not isinstance(max_tool_calls, int)
            or not 1 <= max_tool_calls <= 32
        ):
            raise ValueError(
                "tool-enabled benchmark max_tool_calls must be a positive integer from 1 to 32"
            )
        tool_policy_route = _relative_path(
            raw_tool_policy_route,
            "benchmark tool policy route",
        )
    elif max_tool_calls is not None:
        raise ValueError("tool-free benchmark max_tool_calls must be null")
    elif raw_tool_policy_route is not None:
        raise ValueError("tool-free benchmark tool_policy_route must be null")
    else:
        tool_policy_route = None
    return BenchmarkRecord(
        _nonempty(payload["id"], "benchmark ID"),
        _nonempty(payload["title"], "benchmark title"),
        _relative_path(payload["cases_route"], "benchmark cases route"),
        _strategy_record(payload["grader"], "benchmark grader"),
        _strategy_record(payload["aggregator"], "benchmark aggregator"),
        tools,
        max_tool_calls,
        tool_policy_route,
    )


def _strategy_record(value: object, label: str) -> StrategyRecord:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    kind = _public_id(value.get("kind"), f"{label} kind")
    route = _relative_path(value.get("route"), f"{label} route")
    if kind != "rubric":
        _exact_fields(value, {"kind", "route"}, label)
        return StrategyRecord(kind, route)
    _exact_fields(value, {"kind", "route", "model", "prompt", "passes", "params"}, label)
    passes = value["passes"]
    if isinstance(passes, bool) or not isinstance(passes, int) or passes < 1:
        raise ValueError(f"{label} passes must be a positive integer")
    params = value["params"]
    if not isinstance(params, dict):
        raise TypeError(f"{label} params must be an object")
    parameter_items = tuple(
        (_public_id(key, f"{label} parameter name"), _parameter(item, f"{label} {key!r}"))
        for key, item in params.items()
    )
    return StrategyRecord(
        kind,
        route,
        _nonempty(value["model"], f"{label} model"),
        _nonempty(value["prompt"], f"{label} prompt"),
        passes,
        parameter_items,
    )


def _parameter(value: object, label: str) -> ParameterValue:
    if isinstance(value, bool) or isinstance(value, str | int | float):
        return value
    raise TypeError(f"{label} must be a string, number, or boolean")


def _limits(value: object) -> int:
    if not isinstance(value, dict):
        raise TypeError("engine limits must be an object")
    _exact_fields(value, {"max_request_target_bytes"}, "engine limits")
    limit = value["max_request_target_bytes"]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("max_request_target_bytes must be a positive integer")
    return limit


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


def _public_id(value: object, label: str) -> str:
    identifier = _nonempty(value, label)
    if identifier != identifier.lower() or not all(
        character.isalnum() or character in {"_", "-"} for character in identifier
    ):
        raise ValueError(f"{label} must use lowercase letters, digits, underscores, or hyphens")
    return identifier


def _unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {label} ID")
