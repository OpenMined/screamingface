"""Typed catalogue adapters at the SF Engine HTTP seam."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import NoReturn, cast

import httpx

from screamingface._catalog_view import _BenchmarkCatalog, _ModelCatalog
from screamingface.discovery import BenchmarkInfo, ModelInfo, ScoreDirection
from screamingface.errors import AuthenticationError, PlanningError

_MODELS_PATH = "/v1/models"
_BENCHMARKS_PATH = "/v1/benchmarks"


class Models:
    """Synchronous Model catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response]) -> None:
        self._get = get

    def list(self) -> Sequence[ModelInfo]:
        return _decode_models(_sync_json(self._get, _MODELS_PATH, "Model catalogue"))


class Benchmarks:
    """Synchronous Benchmark catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response]) -> None:
        self._get = get

    def list(self) -> Sequence[BenchmarkInfo]:
        return _decode_benchmarks(_sync_json(self._get, _BENCHMARKS_PATH, "Benchmark catalogue"))


class AsyncModels:
    """Asynchronous Model catalogue bound to one AsyncClient."""

    def __init__(self, get: Callable[[str], Awaitable[httpx.Response]]) -> None:
        self._get = get

    async def list(self) -> Sequence[ModelInfo]:
        return _decode_models(await _async_json(self._get, _MODELS_PATH, "Model catalogue"))


class AsyncBenchmarks:
    """Asynchronous Benchmark catalogue bound to one AsyncClient."""

    def __init__(self, get: Callable[[str], Awaitable[httpx.Response]]) -> None:
        self._get = get

    async def list(self) -> Sequence[BenchmarkInfo]:
        return _decode_benchmarks(
            await _async_json(self._get, _BENCHMARKS_PATH, "Benchmark catalogue")
        )


def _sync_json(
    get: Callable[[str], httpx.Response],
    path: str,
    label: str,
) -> object:
    try:
        response = get(path)
    except httpx.HTTPError as exc:
        _unreachable(label, exc)
    return _response_json(response, label)


async def _async_json(
    get: Callable[[str], Awaitable[httpx.Response]],
    path: str,
    label: str,
) -> object:
    try:
        response = await get(path)
    except httpx.HTTPError as exc:
        _unreachable(label, exc)
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
    root = _mapping(payload, "model catalogue")
    if root.get("object") != "list":
        _invalid("model catalogue object must be 'list'")
    rows = root.get("data")
    if not isinstance(rows, list):
        _invalid("model catalogue must contain a data array")
    values = []
    for row in rows:
        item = _mapping(row, "model catalogue entry")
        try:
            values.append(
                ModelInfo(
                    id=_text(item.get("id"), "Model id"),
                    provider=_text(item.get("owned_by"), "Model provider"),
                )
            )
        except (TypeError, ValueError) as exc:
            _invalid(str(exc))
    return _ModelCatalog(values)


def _decode_benchmarks(payload: object) -> Sequence[BenchmarkInfo]:
    rows = _mapping(payload, "Benchmark catalogue").get("benchmarks")
    if not isinstance(rows, list):
        _invalid("Benchmark catalogue must contain a benchmarks array")
    values = []
    for row in rows:
        item = _mapping(row, "Benchmark catalogue entry")
        try:
            values.append(
                BenchmarkInfo(
                    name=_text(item.get("name"), "Benchmark name"),
                    id=_text(item.get("id"), "Benchmark id"),
                    manifest_digest=_text(item.get("manifest_digest"), "Benchmark manifest digest"),
                    title=_text(item.get("title"), "Benchmark title"),
                    case_count=_positive(item.get("case_count"), "Benchmark case count"),
                    primary_metric=_text(item.get("primary_metric"), "Benchmark primary metric"),
                    score_direction=_direction(item.get("score_direction")),
                )
            )
        except (TypeError, ValueError) as exc:
            _invalid(str(exc))
    return _BenchmarkCatalog(values)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object")
    return cast(Mapping[str, object], value)


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
        _invalid("Benchmark score direction must be maximize or minimize")
    return cast(ScoreDirection, value)


def _unreachable(label: str, cause: Exception) -> NoReturn:
    raise PlanningError(
        f"Could not reach the SF Engine {label}",
        code="engine_unreachable",
        permanent=False,
    ) from cause


def _invalid(message: str) -> NoReturn:
    raise PlanningError(
        message,
        code="invalid_catalogue",
        permanent=True,
    )


__all__ = ["AsyncBenchmarks", "AsyncModels", "Benchmarks", "Models"]
