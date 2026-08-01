"""Typed catalogue adapters at the SF Engine HTTP seam."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import NoReturn

import httpx

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface._ui.catalog import _BenchmarkCatalog, _ModelCatalog
from screamingface.discovery import ModelInfo
from screamingface.errors import AuthenticationError, EngineUnavailableError, PlanningError

_MODELS_PATH = "/v1/models"
_BENCHMARKS_PATH = "/v1/benchmarks"


@dataclass(frozen=True, slots=True)
class _BenchmarkCatalogData:
    ids: tuple[str, ...]
    default: str | None


class Models:
    """Synchronous Model catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response], engine_url: str) -> None:
        self._get = get
        self._engine_url = engine_url

    def list(self) -> Sequence[ModelInfo]:
        return _decode_models(
            _sync_json(self._get, self._engine_url, _MODELS_PATH, "Model catalogue")
        )


class Benchmarks:
    """Synchronous Benchmark catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response], engine_url: str) -> None:
        self._get = get
        self._engine_url = engine_url

    def list(self) -> Sequence[str]:
        return _decode_benchmarks(
            _sync_json(self._get, self._engine_url, _BENCHMARKS_PATH, "Benchmark catalogue")
        )


class AsyncModels:
    """Asynchronous Model catalogue bound to one AsyncClient."""

    def __init__(
        self,
        get: Callable[[str], Awaitable[httpx.Response]],
        engine_url: str,
    ) -> None:
        self._get = get
        self._engine_url = engine_url

    async def list(self) -> Sequence[ModelInfo]:
        return _decode_models(
            await _async_json(self._get, self._engine_url, _MODELS_PATH, "Model catalogue")
        )


class AsyncBenchmarks:
    """Asynchronous Benchmark catalogue bound to one AsyncClient."""

    def __init__(
        self,
        get: Callable[[str], Awaitable[httpx.Response]],
        engine_url: str,
    ) -> None:
        self._get = get
        self._engine_url = engine_url

    async def list(self) -> Sequence[str]:
        return _decode_benchmarks(
            await _async_json(
                self._get,
                self._engine_url,
                _BENCHMARKS_PATH,
                "Benchmark catalogue",
            )
        )


def _sync_json(
    get: Callable[[str], httpx.Response],
    engine_url: str,
    path: str,
    label: str,
) -> object:
    try:
        response = get(path)
    except httpx.HTTPError as exc:
        _unreachable(engine_url, label, exc)
    return _response_json(response, label)


async def _async_json(
    get: Callable[[str], Awaitable[httpx.Response]],
    engine_url: str,
    path: str,
    label: str,
) -> object:
    try:
        response = await get(path)
    except httpx.HTTPError as exc:
        _unreachable(engine_url, label, exc)
    return _response_json(response, label)


def _response_json(response: httpx.Response, label: str) -> object:
    if response.status_code in {401, 403}:
        raise AuthenticationError(
            f"SF Engine authentication is required for {label}",
            code="authentication_required",
            status=response.status_code,
            permanent=True,
        )
    if not response.is_success:
        raise PlanningError(
            f"Could not load the SF Engine {label}: HTTP {response.status_code}",
            code="engine_contract_error",
            status=response.status_code,
            permanent=response.status_code < 500,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise PlanningError(
            f"SF Engine {label} must be JSON",
            code="invalid_catalogue",
            permanent=True,
        ) from exc


def _decode_models(payload: object) -> Sequence[ModelInfo]:
    root = _wire_mapping(payload, "model catalogue", _invalid)
    if root.get("object") != "list":
        _invalid("model catalogue object must be 'list'")
    rows = root.get("data")
    if not isinstance(rows, list):
        _invalid("model catalogue must contain a data array")
    values = []
    for row in rows:
        item = _wire_mapping(row, "model catalogue entry", _invalid)
        try:
            values.append(
                ModelInfo(
                    id=_wire_text(item.get("id"), "Model id", _invalid),
                    provider=_wire_text(item.get("owned_by"), "Model provider", _invalid),
                )
            )
        except (TypeError, ValueError) as exc:
            _invalid(str(exc))
    return _ModelCatalog(values)


def _decode_benchmarks(payload: object) -> Sequence[str]:
    try:
        catalog = _decode_benchmark_catalog(payload)
    except ValueError as exc:
        _invalid(str(exc))
    return _BenchmarkCatalog(catalog.ids)


def _decode_benchmark_catalog(payload: object) -> _BenchmarkCatalogData:
    root = _wire_mapping(payload, "Benchmark catalog", _catalog_invalid)
    if root.get("object") != "list":
        _catalog_invalid("Benchmark catalog object must be 'list'")
    if "default" not in root:
        _catalog_invalid("Benchmark catalog must declare default")
    rows = root.get("data")
    if not isinstance(rows, list):
        _catalog_invalid("Benchmark catalog must contain a data array")
    ids = _benchmark_ids(rows)
    return _BenchmarkCatalogData(ids=ids, default=_benchmark_default(root["default"], ids))


def _benchmark_ids(rows: list[object]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        item = _wire_mapping(row, "Benchmark catalog entry", _catalog_invalid)
        if item.get("object") != "benchmark":
            _catalog_invalid("Benchmark catalog entry object must be 'benchmark'")
        benchmark_id = _wire_text(item.get("id"), "Benchmark id", _catalog_invalid)
        if benchmark_id in seen:
            _catalog_invalid(f"Benchmark catalog contains duplicate id {benchmark_id!r}")
        seen.add(benchmark_id)
        values.append(benchmark_id)
    return tuple(values)


def _benchmark_default(value: object, ids: tuple[str, ...]) -> str | None:
    if not ids:
        if value is not None:
            _catalog_invalid("Empty Benchmark catalog default must be null")
        return None
    selected = _wire_text(value, "Benchmark catalog default", _catalog_invalid)
    if selected not in ids:
        _catalog_invalid(f"Benchmark catalog default {selected!r} is not installed")
    return selected


def _catalog_invalid(message: str) -> NoReturn:
    raise ValueError(message)


def _unreachable(engine_url: str, label: str, cause: Exception) -> NoReturn:
    raise EngineUnavailableError(
        f"Could not reach the SF Engine {label}",
        engine_url=engine_url,
    ) from cause


def _invalid(message: str) -> NoReturn:
    raise PlanningError(
        message,
        code="invalid_catalogue",
        permanent=True,
    )


__all__ = ["AsyncBenchmarks", "AsyncModels", "Benchmarks", "Models"]
