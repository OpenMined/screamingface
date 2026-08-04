"""Typed catalogue adapters at the SF Engine HTTP seam."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn
from urllib.parse import quote

import httpx

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface._ui.catalog import _BenchmarkCatalog, _CaseCatalog, _ModelCatalog
from screamingface.discovery import Benchmark, CaseInfo, ModelInfo
from screamingface.errors import AuthenticationError, EngineUnavailableError, PlanningError

_MODELS_PATH = "/v1/models"
_BENCHMARKS_PATH = "/v1/benchmarks"


@dataclass(frozen=True, slots=True)
class _BenchmarkEntry:
    id: str
    family: str
    variant: str
    title: str
    description: str
    resource_id: str


@dataclass(frozen=True, slots=True)
class _BenchmarkCatalogData:
    entries: tuple[_BenchmarkEntry, ...]
    default: str | None


@dataclass(frozen=True, slots=True)
class _ModelCatalogData:
    models: Sequence[ModelInfo]
    default_synthesizer: str


@dataclass(frozen=True, slots=True)
class _BenchmarkSummary:
    revision: str
    case_count: int


@dataclass(frozen=True, slots=True)
class _CasePage:
    total: int
    limit: int
    offset: int
    rows: tuple[CaseInfo, ...]


class Models:
    """Synchronous Model catalogue bound to one Client."""

    def __init__(self, get: Callable[[str], httpx.Response], engine_url: str) -> None:
        self._get = get
        self._engine_url = engine_url

    def list(self) -> Sequence[ModelInfo]:
        return self._load().models

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
        resources: dict[str, object] = {}
        values = []
        for entry in catalog.entries:
            if entry.resource_id not in resources:
                resources[entry.resource_id] = _sync_json(
                    self._get,
                    self._engine_url,
                    _summary_path(entry.resource_id),
                    "Benchmark resource",
                )
            values.append(self._benchmark(entry, resources[entry.resource_id]))
        return _BenchmarkCatalog(tuple(values))

    def get(self, benchmark_id: str) -> Benchmark:
        catalog = _decode_benchmarks(
            _sync_json(self._get, self._engine_url, _BENCHMARKS_PATH, "Benchmark catalogue")
        )
        entry = _entry_of(catalog, benchmark_id)
        resource = _sync_json(
            self._get,
            self._engine_url,
            _summary_path(entry.resource_id),
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
                _cases_path(entry.resource_id, limit, offset),
                "Benchmark cases",
            )
        )
        return _CaseCatalog(page.rows, total=page.total, limit=page.limit, offset=page.offset)

    def _benchmark(self, entry: _BenchmarkEntry, resource: object) -> Benchmark:
        summary = _decode_benchmark_summary(resource, entry)

        # WHY: the value carries a bound page-fetcher instead of a client so it stays a
        # frozen comparable; `benchmark.cases(...)` is this adapter's `cases` in disguise.
        def fetch(limit: int, offset: int, resource_id: str = entry.resource_id) -> _CaseCatalog:
            page = _decode_case_page(
                _sync_json(
                    self._get,
                    self._engine_url,
                    _cases_path(resource_id, limit, offset),
                    "Benchmark cases",
                )
            )
            return _CaseCatalog(page.rows, total=page.total, limit=page.limit, offset=page.offset)

        return Benchmark(
            id=entry.id,
            family=entry.family,
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
        resources: dict[str, object] = {}
        values = []
        for entry in catalog.entries:
            if entry.resource_id not in resources:
                resources[entry.resource_id] = await _async_json(
                    self._get,
                    self._engine_url,
                    _summary_path(entry.resource_id),
                    "Benchmark resource",
                )
            values.append(self._benchmark(entry, resources[entry.resource_id]))
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
            _summary_path(entry.resource_id),
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
                _cases_path(entry.resource_id, limit, offset),
                "Benchmark cases",
            )
        )
        return _CaseCatalog(page.rows, total=page.total, limit=page.limit, offset=page.offset)

    def _benchmark(self, entry: _BenchmarkEntry, resource: object) -> Benchmark:
        summary = _decode_benchmark_summary(resource, entry)
        return Benchmark(
            id=entry.id,
            family=entry.family,
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
    # WHY limit=1: discovery needs only revision + total_case_count; the unbounded
    # resource would make the Engine render the full url4 expression per catalog row.
    return f"{_BENCHMARKS_PATH}/{quote(benchmark_id, safe='')}?limit=1"


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


def _decode_model_catalog(payload: object) -> _ModelCatalogData:
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
    models = _ModelCatalog(values)
    default_synthesizer = _wire_text(
        root.get("default_synthesizer"),
        "Model catalogue default_synthesizer",
        _invalid,
    )
    if default_synthesizer not in {model.id for model in models}:
        _invalid(f"Model catalogue default synthesizer {default_synthesizer!r} is not installed")
    return _ModelCatalogData(models=models, default_synthesizer=default_synthesizer)


def _decode_benchmarks(payload: object) -> _BenchmarkCatalogData:
    try:
        return _decode_benchmark_catalog(payload)
    except ValueError as exc:
        _invalid(str(exc))


def _decode_benchmark_catalog(payload: object) -> _BenchmarkCatalogData:
    root = _wire_mapping(payload, "Benchmark catalog", _catalog_invalid)
    if root.get("object") != "list":
        _catalog_invalid("Benchmark catalog object must be 'list'")
    if "default" not in root:
        _catalog_invalid("Benchmark catalog must declare default")
    rows = root.get("data")
    if not isinstance(rows, list):
        _catalog_invalid("Benchmark catalog must contain a data array")
    entries = _benchmark_entries(rows)
    ids = tuple(entry.id for entry in entries)
    return _BenchmarkCatalogData(
        entries=entries,
        default=_benchmark_default(root["default"], ids),
    )


def _benchmark_entries(rows: list[object]) -> tuple[_BenchmarkEntry, ...]:
    values: list[_BenchmarkEntry] = []
    seen: set[str] = set()
    for row in rows:
        item = _wire_mapping(row, "Benchmark catalog entry", _catalog_invalid)
        object_type = item.get("object")
        if object_type == "benchmark":
            entries = (_legacy_benchmark_entry(item),)
        elif object_type == "benchmark_family":
            entries = _family_benchmark_entries(item)
        else:
            _catalog_invalid(
                "Benchmark catalog entry object must be 'benchmark' or 'benchmark_family'"
            )
        for entry in entries:
            if entry.id in seen:
                _catalog_invalid(f"Benchmark catalog contains duplicate id {entry.id!r}")
            seen.add(entry.id)
            values.append(entry)
    return tuple(values)


def _legacy_benchmark_entry(item: Mapping[str, object]) -> _BenchmarkEntry:
    benchmark_id = _wire_text(item.get("id"), "Benchmark id", _catalog_invalid)
    return _BenchmarkEntry(
        id=benchmark_id,
        # Additive compatibility: an older Engine exposed only standalone entries.
        family=_wire_text(item.get("family", benchmark_id), "Benchmark family", _catalog_invalid),
        variant=_wire_text(item.get("variant", "canonical"), "Benchmark variant", _catalog_invalid),
        title=_wire_text(item.get("title"), "Benchmark title", _catalog_invalid),
        description=_wire_text(item.get("description"), "Benchmark description", _catalog_invalid),
        resource_id=benchmark_id,
    )


def _family_benchmark_entries(item: Mapping[str, object]) -> tuple[_BenchmarkEntry, ...]:
    family_id = _wire_text(item.get("id"), "Benchmark Family id", _catalog_invalid)
    default_variant = _wire_text(
        item.get("default_variant"), "Benchmark Family default Variant", _catalog_invalid
    )
    variants = item.get("variants")
    if not isinstance(variants, list) or not variants:
        _catalog_invalid("Benchmark Family variants must be a non-empty array")
    selected: list[_BenchmarkEntry] = []
    seen: set[str] = set()
    for raw_variant in variants:
        variant = _wire_mapping(raw_variant, "Benchmark Variant", _catalog_invalid)
        variant_id = _wire_text(variant.get("id"), "Benchmark Variant id", _catalog_invalid)
        if variant_id in seen:
            _catalog_invalid(
                f"Benchmark Family {family_id!r} contains duplicate Variant {variant_id!r}"
            )
        seen.add(variant_id)
        selected.append(
            _BenchmarkEntry(
                id=family_id if variant_id == default_variant else f"{family_id}/{variant_id}",
                family=family_id,
                variant=variant_id,
                title=_wire_text(variant.get("title"), "Benchmark Variant title", _catalog_invalid),
                description=_wire_text(
                    variant.get("description"),
                    "Benchmark Variant description",
                    _catalog_invalid,
                ),
                resource_id=family_id,
            )
        )
    if default_variant not in seen:
        _catalog_invalid(f"Benchmark Family default Variant {default_variant!r} is not installed")
    return tuple(selected)


def _benchmark_default(value: object, ids: tuple[str, ...]) -> str | None:
    if not ids:
        if value is not None:
            _catalog_invalid("Empty Benchmark catalog default must be null")
        return None
    selected = _wire_text(value, "Benchmark catalog default", _catalog_invalid)
    if selected not in ids:
        _catalog_invalid(f"Benchmark catalog default {selected!r} is not installed")
    return selected


def _decode_benchmark_summary(payload: object, entry: _BenchmarkEntry) -> _BenchmarkSummary:
    root = _wire_mapping(payload, "Benchmark resource", _invalid)
    if root.get("schema") == "screamingface.benchmark-family.v1":
        family_id = _wire_text(root.get("id"), "Benchmark Family id", _invalid)
        if family_id != entry.family:
            _invalid("Benchmark resource has the wrong Benchmark Family id")
        variants = _wire_mapping(root.get("variants"), "Benchmark Variants", _invalid)
        if entry.variant not in variants:
            _invalid(f"Benchmark Variant {entry.variant!r} is not installed in {entry.family!r}")
        selected = _wire_mapping(
            variants[entry.variant], f"Benchmark Variant {entry.variant!r}", _invalid
        )
    else:
        selected = root
    revision = _wire_text(selected.get("revision"), "Benchmark revision", _invalid)
    total = selected.get("total_case_count")
    if isinstance(total, bool) or not isinstance(total, int) or total < 1:
        _invalid("Benchmark total_case_count must be a positive integer")
    return _BenchmarkSummary(revision=revision, case_count=total)


def _decode_case_page(payload: object) -> _CasePage:
    root = _wire_mapping(payload, "Benchmark cases page", _invalid)
    if root.get("object") != "list":
        _invalid("Benchmark cases page object must be 'list'")
    counters: dict[str, int] = {}
    for name, minimum in (("total", 0), ("limit", 1), ("offset", 0)):
        value = root.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            _invalid(f"Benchmark cases page {name} must be an integer >= {minimum}")
        counters[name] = value
    rows = root.get("data")
    if not isinstance(rows, list):
        _invalid("Benchmark cases page must contain a data array")
    cases: list[CaseInfo] = []
    for row in rows:
        item = _wire_mapping(row, "Benchmark case", _invalid)
        case_id = item.get("id")
        if isinstance(case_id, bool) or not isinstance(case_id, int):
            _invalid("Benchmark case id must be an integer")
        try:
            cases.append(
                CaseInfo(
                    id=case_id,
                    input=_wire_text(item.get("input"), "Benchmark case input", _invalid),
                )
            )
        except (TypeError, ValueError) as exc:
            _invalid(str(exc))
    return _CasePage(
        total=counters["total"],
        limit=counters["limit"],
        offset=counters["offset"],
        rows=tuple(cases),
    )


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
