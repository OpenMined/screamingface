"""Synchronous and asynchronous ScreamingFace clients."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from screamingface._benchmark_manifest import _BenchmarkManifest
    from screamingface._evaluation import _Evaluation
    from screamingface._ports import AsyncRunTransport, SyncRunTransport
    from screamingface.events import Event
    from screamingface.recipe import Recipe
    from screamingface.report import Report

DEFAULT_ENGINE_URL = "http://127.0.0.1:9108"


class Client:
    """A reusable synchronous Client configured for one SF Engine origin."""

    def __init__(self, *, engine_url: str = DEFAULT_ENGINE_URL) -> None:
        import httpx

        from screamingface._catalogs import Benchmarks, Models
        from screamingface._registry import _default_transport_registry

        self._engine_url = _engine_origin(engine_url)
        self._closed = False
        self._http = httpx.Client(base_url=self._engine_url, timeout=30.0)
        self._transport: SyncRunTransport = _default_transport_registry().sync(self._engine_url)
        self.models = Models(self._http_get)
        self.benchmarks = Benchmarks(self._http_get)

    @property
    def engine_url(self) -> str:
        return self._engine_url

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._transport.close()
        self._http.close()
        self._closed = True

    def evaluate(
        self,
        candidates: Recipe | Sequence[Recipe],
        *,
        benchmark: str,
        limit: int | None = None,
        on_event: Callable[[Event], None] | None = None,
        progress: bool | None = None,
    ) -> Report:
        """Evaluate one or more Candidates against an Engine-owned Benchmark."""

        from screamingface._result_decoder import report_from_outcomes

        self._require_open()
        _evaluation_options(on_event, progress)
        evaluation = _compile_sync(self._http, candidates, benchmark, limit)
        observer = _sync_event_observer(on_event, progress)
        # INVARIANT: every Candidate compiles successfully before the first paid Run starts.
        outcomes = tuple(
            (candidate, self._transport.run(candidate, observer))
            for candidate in evaluation.candidates
        )
        return report_from_outcomes(evaluation, outcomes)

    def __enter__(self) -> Client:
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("ScreamingFace Client is closed")

    def _http_get(self, path: str) -> httpx.Response:
        self._require_open()
        return self._http.get(path)


class AsyncClient:
    """An asynchronous Client with the same domain interface and result types."""

    def __init__(self, *, engine_url: str = DEFAULT_ENGINE_URL) -> None:
        import httpx

        from screamingface._catalogs import AsyncBenchmarks, AsyncModels
        from screamingface._registry import _default_transport_registry

        self._engine_url = _engine_origin(engine_url)
        self._closed = False
        self._http = httpx.AsyncClient(base_url=self._engine_url, timeout=30.0)
        self._transport: AsyncRunTransport = _default_transport_registry().async_(self._engine_url)
        self.models = AsyncModels(self._http_get)
        self.benchmarks = AsyncBenchmarks(self._http_get)

    @property
    def engine_url(self) -> str:
        return self._engine_url

    @property
    def closed(self) -> bool:
        return self._closed

    async def aclose(self) -> None:
        if self._closed:
            return
        await self._transport.close()
        await self._http.aclose()
        self._closed = True

    async def evaluate(
        self,
        candidates: Recipe | Sequence[Recipe],
        *,
        benchmark: str,
        limit: int | None = None,
        on_event: Callable[[Event], None | Awaitable[None]] | None = None,
        progress: bool | None = None,
    ) -> Report:
        """Asynchronously evaluate Candidates against an Engine-owned Benchmark."""

        from screamingface._result_decoder import report_from_outcomes

        self._require_open()
        _evaluation_options(on_event, progress)
        evaluation = await _compile_async(self._http, candidates, benchmark, limit)
        observer = _async_event_observer(on_event, progress)
        # INVARIANT: every Candidate compiles successfully before the first paid Run starts.
        outcomes = []
        for candidate in evaluation.candidates:
            outcomes.append((candidate, await self._transport.run(candidate, observer)))
        return report_from_outcomes(evaluation, tuple(outcomes))

    async def __aenter__(self) -> AsyncClient:
        self._require_open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("ScreamingFace AsyncClient is closed")

    async def _http_get(self, path: str) -> httpx.Response:
        self._require_open()
        return await self._http.get(path)


def _engine_origin(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("engine_url must be an HTTP(S) origin")
    parts = urlsplit(value.strip())
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("engine_url must be an HTTP(S) origin without credentials or a path")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _evaluation_options(on_event: object, progress: object) -> None:
    if on_event is not None and not callable(on_event):
        raise TypeError("on_event must be callable or None")
    if progress is not None and not isinstance(progress, bool):
        raise TypeError("progress must be True, False, or None")


def _sync_event_observer(
    callback: Callable[[Event], None] | None,
    progress: bool | None,
) -> Callable[[Event], None] | None:
    from screamingface._progress import _progress_observer

    builtin = _progress_observer(progress)
    if builtin is None:
        return callback
    if callback is None:
        return builtin

    def observe(event: Event) -> None:
        builtin(event)
        callback(event)

    return observe


def _async_event_observer(
    callback: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
) -> Callable[[Event], Awaitable[None]] | None:
    import inspect

    from screamingface._progress import _progress_observer

    builtin = _progress_observer(progress)
    if builtin is None and callback is None:
        return None

    async def observe(event: Event) -> None:
        if builtin is not None:
            builtin(event)
        if callback is not None:
            returned = callback(event)
            if inspect.isawaitable(returned):
                await returned

    return observe


def _compile_sync(
    http: httpx.Client,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str,
    limit: int | None,
) -> _Evaluation:
    from screamingface._benchmark_manifest import load_manifest

    values = _evaluation_inputs(candidates, benchmark, limit)
    return _compile(values, load_manifest(http, benchmark), limit)


async def _compile_async(
    http: httpx.AsyncClient,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str,
    limit: int | None,
) -> _Evaluation:
    from screamingface._benchmark_manifest import load_manifest_async

    values = _evaluation_inputs(candidates, benchmark, limit)
    return _compile(values, await load_manifest_async(http, benchmark), limit)


def _compile(
    candidates: tuple[Recipe, ...],
    manifest: _BenchmarkManifest,
    limit: int | None,
) -> _Evaluation:
    from screamingface._compiler import compile_model_benchmark
    from screamingface._evaluation import (
        _candidate_from_engine,
        _evaluation_from_engine,
        _operation_from_engine,
    )
    from screamingface.errors import PlanningError
    from screamingface.model import Model

    case_count = manifest.info.case_count if limit is None else min(limit, manifest.info.case_count)
    compiled = []
    for value in candidates:
        if not isinstance(value, Model):
            raise PlanningError("the first DRACO-Lite vertical demo accepts Model Candidates")
        answer = _operation_from_engine(
            id="op_answer",
            kind="model",
            label=f"{value.name} answer",
            depends_on=(),
        )
        grade = _operation_from_engine(
            id="op_grade",
            kind="grading",
            label="DRACO-Lite rubric grading",
            depends_on=(answer.id,),
        )
        aggregate = _operation_from_engine(
            id="op_aggregate",
            kind="aggregation",
            label="DRACO-Lite mean aggregation",
            depends_on=(grade.id,),
        )
        compiled.append(
            _candidate_from_engine(
                name=value.name,
                kind="model",
                models=(value.model,),
                url4=compile_model_benchmark(value, manifest, limit=case_count),
                operations=(answer, grade, aggregate),
            )
        )
    return _evaluation_from_engine(
        benchmark=manifest.info,
        limit=limit,
        case_count=case_count,
        candidates=compiled,
        capability_profile=manifest.info.manifest_digest,
        required_capabilities=manifest.required_capabilities,
        operation_counts={
            "model": len(compiled) * case_count,
            "grading": len(compiled) * case_count * manifest.criteria_per_case,
            "aggregation": len(compiled),
        },
    )


def _evaluation_inputs(
    candidates: Recipe | Sequence[Recipe],
    benchmark: str,
    limit: int | None,
) -> tuple[Recipe, ...]:
    from screamingface._evaluation import _candidate_values, _validate_limit

    values = _candidate_values(candidates)
    if not isinstance(benchmark, str) or not benchmark.strip():
        raise ValueError("benchmark must be a non-empty string")
    _validate_limit(limit)
    return values


__all__ = ["AsyncClient", "Client", "DEFAULT_ENGINE_URL"]
