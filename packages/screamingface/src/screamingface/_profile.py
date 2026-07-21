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

REGISTRY_PATH = "/.well-known/screamingface"
REGISTRY_SCHEMA = "screamingface.registry.v1"
RECIPE_RESULT_SCHEMA = "screamingface.recipe-result.v1"
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


@dataclass(frozen=True, slots=True)
class ReducerRecord:
    id: str
    route: str


@dataclass(frozen=True, slots=True)
class Registry:
    models: tuple[ModelRecord, ...]
    reducers: tuple[ReducerRecord, ...]
    response_schemas: tuple[str, ...]
    max_request_target_bytes: int
    providers: tuple[ProviderRecord, ...]


def load_registry() -> Registry:
    payload = _json_object(_get_text(REGISTRY_PATH), "engine registry")
    try:
        _exact_fields(
            payload,
            {"schema", "response_schemas", "limits", "providers", "models", "reducers"},
            "engine registry",
        )
        if payload["schema"] != REGISTRY_SCHEMA:
            raise ValueError(f"expected schema {REGISTRY_SCHEMA!r}")
        response_schemas = _string_list(payload["response_schemas"], "response_schemas")
        providers = tuple(
            _provider_record(item) for item in _object_list(payload["providers"], "providers")
        )
        models = tuple(_model_record(item) for item in _object_list(payload["models"], "models"))
        reducers = tuple(
            _reducer_record(item) for item in _object_list(payload["reducers"], "reducers")
        )
        limits = _limits(payload["limits"])
        _unique((record.id for record in models), "model")
        _unique((record.id for record in providers), "provider")
        _unique((record.id for record in reducers), "reducer")
        provider_ids = {record.id for record in providers}
        for model in models:
            if model.provider not in provider_ids:
                raise ValueError(
                    f"model {model.id!r} references unknown provider {model.provider!r}"
                )
        if RECIPE_RESULT_SCHEMA not in response_schemas:
            raise ValueError(f"missing response schema {RECIPE_RESULT_SCHEMA!r}")
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineProfileError(f"invalid engine registry: {exc}") from exc
    return Registry(models, reducers, response_schemas, limits, providers)


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
    _exact_fields(payload, {"id", "provider", "supported_tools"}, "model record")
    return ModelRecord(
        _nonempty(payload["id"], "model ID"),
        tool_ids(
            _string_list(payload["supported_tools"], "model supported_tools"),
            label="model supported_tools",
        ),
        _public_id(payload["provider"], "model provider"),
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
