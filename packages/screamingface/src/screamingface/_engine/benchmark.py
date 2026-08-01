"""HTTP adapter for Engine-owned Benchmark catalogues and manifests."""

from __future__ import annotations

import httpx
import yaml

from screamingface._engine.catalog import _decode_benchmark_catalog
from screamingface._evaluation.benchmark import _BenchmarkManifest, _decode_manifest
from screamingface.errors import EngineUnavailableError, PlanningError


class BenchmarkManifests:
    """Synchronous Benchmark manifest adapter bound to one Engine client."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def load(self, benchmark: str | None = None) -> _BenchmarkManifest:
        return load_manifest(self._http, benchmark)


class AsyncBenchmarkManifests:
    """Asynchronous Benchmark manifest adapter bound to one Engine client."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def load(self, benchmark: str | None = None) -> _BenchmarkManifest:
        return await load_manifest_async(self._http, benchmark)


def load_manifest(http: httpx.Client, benchmark: str | None = None) -> _BenchmarkManifest:
    """Resolve one catalogued Engine-owned Benchmark manifest."""

    try:
        catalog_response = http.get("/v1/benchmarks")
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not reach the SF Engine Benchmark catalog",
            engine_url=_engine_url(http),
        ) from exc
    _success(catalog_response, "list Benchmarks")
    selected = _select_benchmark(catalog_response, benchmark)

    try:
        manifest_response = http.get(f"/v1/benchmarks/{selected}")
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            f"Could not reach SF Engine Benchmark {selected!r}",
            engine_url=_engine_url(http),
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
        raise EngineUnavailableError(
            "Could not reach the SF Engine Benchmark catalog",
            engine_url=_engine_url(http),
        ) from exc
    _success(catalog_response, "list Benchmarks")
    selected = _select_benchmark(catalog_response, benchmark)

    try:
        manifest_response = await http.get(f"/v1/benchmarks/{selected}")
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            f"Could not reach SF Engine Benchmark {selected!r}",
            engine_url=_engine_url(http),
        ) from exc
    _success(manifest_response, f"load Benchmark {selected!r}")
    return _verified_manifest(manifest_response)


def _verified_manifest(manifest_response: httpx.Response) -> _BenchmarkManifest:
    try:
        decoded = yaml.safe_load(manifest_response.content)
    except yaml.YAMLError as exc:
        raise PlanningError(
            "SF Engine Benchmark manifest is not valid YAML",
            code="invalid_benchmark_manifest",
            permanent=True,
        ) from exc
    return _decode_manifest(decoded)


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


def _engine_url(http: httpx.Client | httpx.AsyncClient) -> str:
    return str(http.base_url).rstrip("/")


__all__: list[str] = []
