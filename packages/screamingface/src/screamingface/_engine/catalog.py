"""Typed catalogue adapters at the SF Engine HTTP seam."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import NoReturn
from urllib.parse import quote

import httpx

from screamingface._engine.catalog_contract import (
    _BenchmarkCatalogData,
    _BenchmarkEntry,
    _decode_benchmark_summary,
    _decode_benchmarks,
    _decode_case_page,
    _decode_model_catalog,
    _ModelCatalogData,
)
from screamingface._engine.model_parameters import _decode_model_details
from screamingface._ui.catalog import _BenchmarkCatalog, _CaseCatalog
from screamingface.discovery import Benchmark, ModelDetails, ModelInfo
from screamingface.errors import (
    AuthenticationError,
    EngineUnavailableError,
    PlanningError,
    ProviderConnectionError,
)

_MODELS_PATH = "/v1/models"
_MODEL_PARAMETERS_PATH = "/v1/model-parameters"
_BENCHMARKS_PATH = "/v1/benchmarks"


class Models:
    """Synchronous Model catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response], engine_url: str) -> None:
        self._get = get
        self._engine_url = engine_url

    def list(self) -> Sequence[ModelInfo]:
        return self._load().models

    def get(self, model_id: str) -> ModelDetails:
        """Fetch profile-specific details for one canonical Model id."""

        selected = _model_id(model_id)
        return _decode_model_details(
            _sync_json(
                self._get,
                self._engine_url,
                _model_parameters_path(selected),
                "Model details",
            ),
            selected,
        )

    def _load(self) -> _ModelCatalogData:
        return _decode_model_catalog(
            _sync_json(self._get, self._engine_url, _MODELS_PATH, "Model catalogue")
        )


class Benchmarks:
    """Synchronous Benchmark catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response], engine_url: str) -> None:
        self._get = get
        self._engine_url = engine_url

    def list(self) -> Sequence[Benchmark]:
        catalog = _decode_benchmarks(
            _sync_json(self._get, self._engine_url, _BENCHMARKS_PATH, "Benchmark catalogue")
        )
        values = []
        for entry in catalog.entries:
            resource = _sync_json(
                self._get,
                self._engine_url,
                _summary_path(entry.id),
                "Benchmark resource",
            )
            values.append(self._benchmark(entry, resource))
        return _BenchmarkCatalog(tuple(values))

    def get(self, benchmark_id: str) -> Benchmark:
        catalog = _decode_benchmarks(
            _sync_json(self._get, self._engine_url, _BENCHMARKS_PATH, "Benchmark catalogue")
        )
        entry = _entry_of(catalog, benchmark_id)
        resource = _sync_json(
            self._get,
            self._engine_url,
            _summary_path(entry.id),
            "Benchmark resource",
        )
        return self._benchmark(entry, resource)

    def cases(self, benchmark_id: str, *, limit: int = 50, offset: int = 0) -> _CaseCatalog:
        catalog = _decode_benchmarks(
            _sync_json(self._get, self._engine_url, _BENCHMARKS_PATH, "Benchmark catalogue")
        )
        entry = _entry_of(catalog, benchmark_id)
        page = _decode_case_page(
            _sync_json(
                self._get,
                self._engine_url,
                _cases_path(entry.id, limit, offset),
                "Benchmark cases",
            )
        )
        return _CaseCatalog(page.rows, total=page.total, limit=page.limit, offset=page.offset)

    def _benchmark(self, entry: _BenchmarkEntry, resource: object) -> Benchmark:
        summary = _decode_benchmark_summary(resource, entry)

        # WHY: the value carries a bound page-fetcher instead of a client so it stays a
        # frozen comparable; `benchmark.cases(...)` is this adapter's `cases` in disguise.
        def fetch(limit: int, offset: int, benchmark_id: str = entry.id) -> _CaseCatalog:
            page = _decode_case_page(
                _sync_json(
                    self._get,
                    self._engine_url,
                    _cases_path(benchmark_id, limit, offset),
                    "Benchmark cases",
                )
            )
            return _CaseCatalog(page.rows, total=page.total, limit=page.limit, offset=page.offset)

        return Benchmark(
            id=entry.id,
            variant=entry.variant,
            title=entry.title,
            description=entry.description,
            revision=summary.revision,
            case_count=summary.case_count,
            _fetch_cases=fetch,
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
        return (await self._load()).models

    async def get(self, model_id: str) -> ModelDetails:
        """Fetch profile-specific details for one canonical Model id."""

        selected = _model_id(model_id)
        return _decode_model_details(
            await _async_json(
                self._get,
                self._engine_url,
                _model_parameters_path(selected),
                "Model details",
            ),
            selected,
        )

    async def _load(self) -> _ModelCatalogData:
        return _decode_model_catalog(
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

    async def list(self) -> Sequence[Benchmark]:
        catalog = _decode_benchmarks(
            await _async_json(
                self._get,
                self._engine_url,
                _BENCHMARKS_PATH,
                "Benchmark catalogue",
            )
        )
        values = []
        for entry in catalog.entries:
            resource = await _async_json(
                self._get,
                self._engine_url,
                _summary_path(entry.id),
                "Benchmark resource",
            )
            values.append(self._benchmark(entry, resource))
        return _BenchmarkCatalog(tuple(values))

    async def get(self, benchmark_id: str) -> Benchmark:
        catalog = _decode_benchmarks(
            await _async_json(
                self._get,
                self._engine_url,
                _BENCHMARKS_PATH,
                "Benchmark catalogue",
            )
        )
        entry = _entry_of(catalog, benchmark_id)
        resource = await _async_json(
            self._get,
            self._engine_url,
            _summary_path(entry.id),
            "Benchmark resource",
        )
        return self._benchmark(entry, resource)

    async def cases(self, benchmark_id: str, *, limit: int = 50, offset: int = 0) -> _CaseCatalog:
        catalog = _decode_benchmarks(
            await _async_json(
                self._get,
                self._engine_url,
                _BENCHMARKS_PATH,
                "Benchmark catalogue",
            )
        )
        entry = _entry_of(catalog, benchmark_id)
        page = _decode_case_page(
            await _async_json(
                self._get,
                self._engine_url,
                _cases_path(entry.id, limit, offset),
                "Benchmark cases",
            )
        )
        return _CaseCatalog(page.rows, total=page.total, limit=page.limit, offset=page.offset)

    def _benchmark(self, entry: _BenchmarkEntry, resource: object) -> Benchmark:
        summary = _decode_benchmark_summary(resource, entry)
        return Benchmark(
            id=entry.id,
            variant=entry.variant,
            title=entry.title,
            description=entry.description,
            revision=summary.revision,
            case_count=summary.case_count,
            _fetch_cases=_async_cases_redirect(entry.id),
        )


def _async_cases_redirect(benchmark_id: str) -> Callable[[int, int], _CaseCatalog]:
    # WHY: an async-born value cannot page synchronously; failing loudly with the exact
    # replacement call beats returning an un-awaited coroutine from a sync-looking API.
    def redirect(limit: int, offset: int) -> _CaseCatalog:
        raise PlanningError(
            "This Benchmark came from an AsyncClient — page its cases with "
            f"await client.benchmarks.cases({benchmark_id!r}, limit=…, offset=…)",
            code="sync_cases_on_async_client",
            permanent=True,
        )

    return redirect


def _summary_path(benchmark_id: str) -> str:
    # WHY limit=1: discovery needs only revision + installed case_count; the unbounded
    # resource would make the Engine render the full url4 expression per catalog row.
    return f"{_BENCHMARKS_PATH}/{quote(benchmark_id, safe='')}?limit=1"


def _model_parameters_path(model_id: str) -> str:
    return f"{_MODEL_PARAMETERS_PATH}?model={quote(model_id, safe='')}"


def _model_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("model_id must be a string")
    selected = value.removeprefix("/").strip()
    if not selected:
        raise ValueError("model_id must be a non-empty string")
    return selected


def _cases_path(benchmark_id: str, limit: int, offset: int) -> str:
    return f"{_BENCHMARKS_PATH}/{quote(benchmark_id, safe='')}/cases?limit={limit}&offset={offset}"


def _entry_of(catalog: _BenchmarkCatalogData, benchmark_id: str) -> _BenchmarkEntry:
    for entry in catalog.entries:
        if entry.id == benchmark_id:
            return entry
    raise PlanningError(
        f"Benchmark {benchmark_id!r} is not installed on this Engine",
        code="unknown_benchmark",
        permanent=True,
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
    if label == "Model details" and not response.is_success:
        _raise_model_details_error(response)
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


def _raise_model_details_error(response: httpx.Response) -> None:
    """Preserve AI Gateway's profile/model diagnostic relayed by the Engine."""

    try:
        root = response.json()
    except ValueError:
        return
    if not isinstance(root, Mapping) or not isinstance(root.get("detail"), Mapping):
        return
    detail = root["detail"]
    code = detail.get("code")
    provider = detail.get("provider")
    profile = detail.get("name")
    if (
        code in {"profile_not_found", "profile_pending_auth", "auth_required"}
        and isinstance(provider, str)
        and isinstance(profile, str)
    ):
        display = provider.replace("-", " ").title()
        messages = {
            "profile_not_found": f"{display} profile {profile!r} is not connected",
            "profile_pending_auth": f"{display} profile {profile!r} is still connecting",
            "auth_required": f"{display} profile {profile!r} must be reconnected",
        }
        actions = {
            "profile_not_found": "connect",
            "profile_pending_auth": "finish connecting",
            "auth_required": "reconnect",
        }
        raise ProviderConnectionError(
            messages[code],
            provider=provider,
            code=code,
            status=response.status_code,
            permanent=code != "profile_pending_auth",
            details=dict(detail),
            hint=f"Open `sf.connect()` and {actions[code]} {display}, then retry.",
        )
    if code == "model_not_found" and isinstance(detail.get("model"), str):
        model = detail["model"]
        raise PlanningError(
            f"Model {model!r} is not available from the selected provider profile",
            code="model_not_found",
            status=response.status_code,
            permanent=True,
            details=dict(detail),
        )


def _unreachable(engine_url: str, label: str, cause: Exception) -> NoReturn:
    raise EngineUnavailableError(
        f"Could not reach the SF Engine {label}",
        engine_url=engine_url,
    ) from cause


__all__ = ["AsyncBenchmarks", "AsyncModels", "Benchmarks", "Models"]
