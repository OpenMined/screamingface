"""Synchronous and asynchronous ScreamingFace clients."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any, overload
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from screamingface._benchmark_manifest import _BenchmarkManifest
    from screamingface._connection_panel import ConnectionPanel
    from screamingface._evaluation import Candidate, _Evaluation
    from screamingface._ports import AsyncRunTransport, SyncRunTransport, _RunOutcome
    from screamingface.connections import Connection
    from screamingface.discovery import ModelInfo
    from screamingface.events import Event
    from screamingface.recipe import Recipe
    from screamingface.report import Report

DEFAULT_ENGINE_URL = "http://127.0.0.1:9108"
_MAX_CANDIDATES_IN_FLIGHT = 8


class _AuthListeners:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._callbacks: set[Callable[[], None]] = set()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            self._callbacks.add(callback)

        def unsubscribe() -> None:
            with self._lock:
                self._callbacks.discard(callback)

        return unsubscribe

    def notify(self) -> None:
        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            callback()


class Client:
    """A reusable synchronous Client configured for one SF Engine origin."""

    def __init__(self, *, engine_url: str = DEFAULT_ENGINE_URL) -> None:
        import httpx

        from screamingface._authentication import _default_caller_auth
        from screamingface._catalogs import Benchmarks, Models
        from screamingface._registry import _default_transport_registry
        from screamingface.connections import Connections

        self._engine_url = _engine_origin(engine_url)
        self._closed = False
        self._auth_listeners = _AuthListeners()
        self._auth = _default_caller_auth(self._engine_url)
        self._http = httpx.Client(base_url=self._engine_url, timeout=30.0, auth=self._auth)
        self._transport: SyncRunTransport = _default_transport_registry().sync(
            self._engine_url,
            self._auth,
        )
        self.models = Models(self._http_get)
        self.benchmarks = Benchmarks(self._http_get)
        self.connections = Connections(self._http_request)

    @property
    def engine_url(self) -> str:
        return self._engine_url

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def authenticated(self) -> bool:
        """Whether this process currently holds hosted caller credentials."""

        return self._auth.authenticated

    @property
    def authenticating(self) -> bool:
        """Whether a hosted caller login is currently waiting for completion."""

        return self._auth.authenticating

    def login(self, *, timeout: float = 300.0) -> None:
        """Authenticate through the Engine's Cloudflare Access browser flow."""

        self._require_open()
        try:
            self._auth.login(timeout=timeout)
        finally:
            self._auth_listeners.notify()

    def _cancel_login(self) -> None:
        self._require_open()
        self._auth.cancel_login()
        self._auth_listeners.notify()

    def _subscribe_auth(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._require_open()
        return self._auth_listeners.subscribe(callback)

    def _access_required(self) -> bool:
        self._require_open()
        return self._auth.access_required()

    def logout(self) -> None:
        """Forget caller credentials and start Cloudflare Access browser logout."""

        self._require_open()
        self._auth.logout()
        self._auth_listeners.notify()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._transport.close()
        finally:
            try:
                self._http.close()
            finally:
                self._auth.close()
                self._closed = True

    def evaluate(
        self,
        candidates: Recipe | Sequence[Recipe],
        *,
        benchmark: str | None = None,
        limit: int | None = None,
        on_event: Callable[[Event], None] | None = None,
        progress: bool | None = None,
    ) -> Report:
        """Evaluate one or more Candidates against an Engine-owned Benchmark."""

        from screamingface._result_decoder import report_from_outcomes

        self._require_open()
        _evaluation_options(on_event, progress)
        evaluation = _compile_sync(self._http, candidates, benchmark, limit)
        _validate_required_models(evaluation, self.models.list())
        observer = _sync_event_observer(on_event, progress)
        # INVARIANT: every Candidate compiles successfully before the first paid Run starts.
        outcomes = _run_candidates_sync(
            self._transport,
            tuple(evaluation.candidates),
            observer,
        )
        return report_from_outcomes(evaluation, outcomes)

    @overload
    def connect(
        self,
        provider: None = None,
        *,
        api_key: None = None,
    ) -> ConnectionPanel: ...

    @overload
    def connect(
        self,
        provider: str,
        *,
        api_key: str,
    ) -> Connection: ...

    def connect(
        self,
        provider: str | None = None,
        *,
        api_key: str | None = None,
    ) -> Connection | ConnectionPanel:
        """Open the notebook panel, or connect one provider with an API key."""

        self._require_open()
        if provider is None:
            if api_key is not None:
                raise TypeError("provider is required when api_key is supplied")
            from screamingface._connection_panel import ConnectionPanel

            return ConnectionPanel(self)
        if api_key is None:
            raise ValueError("api_key is required when connecting a provider")
        _require_secure_connection_origin(self._engine_url)
        return self.connections.connect(provider, api_key)

    def disconnect(self, provider: str) -> Connection:
        """Disconnect one provider; repeated calls remain harmless."""

        self._require_open()
        return self.connections.disconnect(provider)

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

    def _http_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
    ) -> httpx.Response:
        self._require_open()
        return self._http.request(method, path, json=json)


class AsyncClient:
    """An asynchronous Client with the same domain interface and result types."""

    def __init__(self, *, engine_url: str = DEFAULT_ENGINE_URL) -> None:
        import httpx

        from screamingface._authentication import _default_caller_auth
        from screamingface._catalogs import AsyncBenchmarks, AsyncModels
        from screamingface._registry import _default_transport_registry
        from screamingface.connections import AsyncConnections

        self._engine_url = _engine_origin(engine_url)
        self._closed = False
        self._auth_listeners = _AuthListeners()
        self._auth = _default_caller_auth(self._engine_url)
        self._http = httpx.AsyncClient(base_url=self._engine_url, timeout=30.0, auth=self._auth)
        self._transport: AsyncRunTransport = _default_transport_registry().async_(
            self._engine_url,
            self._auth,
        )
        self.models = AsyncModels(self._http_get)
        self.benchmarks = AsyncBenchmarks(self._http_get)
        self.connections = AsyncConnections(self._http_request)

    @property
    def engine_url(self) -> str:
        return self._engine_url

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def authenticated(self) -> bool:
        """Whether this process currently holds hosted caller credentials."""

        return self._auth.authenticated

    @property
    def authenticating(self) -> bool:
        """Whether a hosted caller login is currently waiting for completion."""

        return self._auth.authenticating

    async def login(self, *, timeout: float = 300.0) -> None:
        """Authenticate through the Engine's Cloudflare Access browser flow."""

        self._require_open()
        try:
            await self._auth.login_async(timeout=timeout)
        finally:
            self._auth_listeners.notify()

    def _cancel_login(self) -> None:
        self._require_open()
        self._auth.cancel_login()
        self._auth_listeners.notify()

    def _subscribe_auth(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._require_open()
        return self._auth_listeners.subscribe(callback)

    async def _access_required(self) -> bool:
        self._require_open()
        return await asyncio.to_thread(self._auth.access_required)

    async def logout(self) -> None:
        """Forget caller credentials and start Cloudflare Access browser logout."""

        self._require_open()
        await self._auth.logout_async()
        self._auth_listeners.notify()

    async def aclose(self) -> None:
        if self._closed:
            return
        try:
            await self._transport.close()
        finally:
            try:
                await self._http.aclose()
            finally:
                await asyncio.to_thread(self._auth.close)
                self._closed = True

    async def evaluate(
        self,
        candidates: Recipe | Sequence[Recipe],
        *,
        benchmark: str | None = None,
        limit: int | None = None,
        on_event: Callable[[Event], None | Awaitable[None]] | None = None,
        progress: bool | None = None,
    ) -> Report:
        """Asynchronously evaluate Candidates against an Engine-owned Benchmark."""

        from screamingface._result_decoder import report_from_outcomes

        self._require_open()
        _evaluation_options(on_event, progress)
        evaluation = await _compile_async(self._http, candidates, benchmark, limit)
        _validate_required_models(evaluation, await self.models.list())
        observer = _async_event_observer(on_event, progress)
        # INVARIANT: every Candidate compiles successfully before the first paid Run starts.
        outcomes = await _run_candidates_async(
            self._transport,
            tuple(evaluation.candidates),
            observer,
        )
        return report_from_outcomes(evaluation, outcomes)

    async def connect(self, provider: str, *, api_key: str) -> Connection:
        """Connect one provider through this AsyncClient."""

        self._require_open()
        _require_secure_connection_origin(self._engine_url)
        return await self.connections.connect(provider, api_key)

    async def disconnect(self, provider: str) -> Connection:
        """Disconnect one provider through this AsyncClient."""

        self._require_open()
        return await self.connections.disconnect(provider)

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

    async def _http_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
    ) -> httpx.Response:
        self._require_open()
        return await self._http.request(method, path, json=json)


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


def _require_secure_connection_origin(engine_url: str) -> None:
    from screamingface.errors import ProviderConnectionError

    parts = urlsplit(engine_url)
    if parts.scheme == "https" or (
        parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        return
    raise ProviderConnectionError(
        "Provider API keys require HTTPS outside a loopback SF Engine",
        code="secure_transport_required",
        permanent=True,
    )


def _evaluation_options(on_event: object, progress: object) -> None:
    if on_event is not None and not callable(on_event):
        raise TypeError("on_event must be callable or None")
    if progress is not None and not isinstance(progress, bool):
        raise TypeError("progress must be True, False, or None")


def _sync_event_observer(
    callback: Callable[[Event], None] | None,
    progress: bool | None,
) -> Callable[[Event], None] | None:
    from threading import Lock

    from screamingface._progress import _progress_observer

    builtin = _progress_observer(progress)
    if builtin is None and callback is None:
        return None
    lock = Lock()

    def observe(event: Event) -> None:
        with lock:
            if builtin is not None:
                builtin(event)
            if callback is not None:
                callback(event)

    return observe


def _async_event_observer(
    callback: Callable[[Event], None | Awaitable[None]] | None,
    progress: bool | None,
) -> Callable[[Event], Awaitable[None]] | None:
    import asyncio
    import inspect

    from screamingface._progress import _progress_observer

    builtin = _progress_observer(progress)
    if builtin is None and callback is None:
        return None
    lock = asyncio.Lock()

    async def observe(event: Event) -> None:
        async with lock:
            if builtin is not None:
                builtin(event)
            if callback is not None:
                returned = callback(event)
                if inspect.isawaitable(returned):
                    await returned

    return observe


def _run_candidates_sync(
    transport: SyncRunTransport,
    candidates: tuple[Candidate, ...],
    observer: Callable[[Event], None] | None,
) -> tuple[tuple[Candidate, _RunOutcome], ...]:
    if len(candidates) == 1:
        candidate = candidates[0]
        return ((candidate, transport.run(candidate, observer)),)

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(
        max_workers=min(len(candidates), _MAX_CANDIDATES_IN_FLIGHT),
        thread_name_prefix="screamingface-candidate",
    ) as executor:
        futures = tuple(
            executor.submit(transport.run, candidate, observer) for candidate in candidates
        )
        try:
            return tuple(
                (candidate, future.result())
                for candidate, future in zip(candidates, futures, strict=True)
            )
        except BaseException:
            for future in futures:
                future.cancel()
            raise


async def _run_candidates_async(
    transport: AsyncRunTransport,
    candidates: tuple[Candidate, ...],
    observer: Callable[[Event], None | Awaitable[None]] | None,
) -> tuple[tuple[Candidate, _RunOutcome], ...]:
    if len(candidates) == 1:
        candidate = candidates[0]
        return ((candidate, await transport.run(candidate, observer)),)

    import asyncio

    gate = asyncio.Semaphore(_MAX_CANDIDATES_IN_FLIGHT)

    async def run(candidate: Candidate) -> _RunOutcome:
        async with gate:
            return await transport.run(candidate, observer)

    tasks = tuple(asyncio.create_task(run(candidate)) for candidate in candidates)
    try:
        outcomes = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return tuple(zip(candidates, outcomes, strict=True))


def _compile_sync(
    http: httpx.Client,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
    limit: int | None,
) -> _Evaluation:
    from screamingface._benchmark_manifest import load_manifest

    values = _evaluation_inputs(candidates, benchmark, limit)
    return _compile(values, load_manifest(http, benchmark), limit)


async def _compile_async(
    http: httpx.AsyncClient,
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
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
    from screamingface._compiler import compile_benchmark
    from screamingface._evaluation import (
        _candidate_from_engine,
        _evaluation_from_engine,
        _member_projection,
        _operation_from_engine,
    )

    case_count = manifest.info.case_count if limit is None else min(limit, manifest.info.case_count)
    compiled = []
    model_calls = 0
    synthesis_calls = 0
    for value in candidates:
        candidate = compile_benchmark(value, manifest, limit=case_count)
        model_calls += candidate.model_calls_per_case
        synthesis_calls += candidate.synthesis_calls_per_case
        compiled.append(
            _candidate_from_engine(
                name=value.name,
                kind=candidate.kind,
                models=candidate.models,
                url4=candidate.url4,
                operations=tuple(
                    _operation_from_engine(
                        id=operation.id,
                        kind=operation.kind,
                        label=operation.label,
                        depends_on=operation.depends_on,
                    )
                    for operation in candidate.operations
                ),
                members=tuple(
                    _member_projection(
                        operation_id=member.operation_id,
                        name=member.name,
                        kind=member.kind,
                        models=member.models,
                    )
                    for member in candidate.members
                ),
            )
        )
    return _evaluation_from_engine(
        benchmark=manifest.info,
        limit=limit,
        case_count=case_count,
        candidates=compiled,
        required_capabilities=manifest.required_capabilities,
        required_models=tuple(
            dict.fromkeys(
                (
                    *(model for candidate in compiled for model in candidate.models),
                    manifest.judge_model,
                )
            )
        ),
        operation_counts={
            "model": model_calls * case_count,
            "synthesis": synthesis_calls * case_count,
            "judge": (
                len(compiled) * case_count * manifest.criteria_per_case * manifest.judge_passes
            ),
            "grading": len(compiled) * case_count,
            "aggregation": len(compiled),
        },
    )


def _validate_required_models(
    evaluation: _Evaluation,
    available: Sequence[ModelInfo],
) -> None:
    from screamingface.errors import PlanningError

    available_ids = {model.id for model in available}
    missing = tuple(model for model in evaluation.required_models if model not in available_ids)
    if not missing:
        return
    if len(missing) == 1:
        message = f"Model {missing[0]!r} is not available on this Engine"
    else:
        names = ", ".join(repr(model) for model in missing)
        message = f"Models {names} are not available on this Engine"
    raise PlanningError(
        message,
        code="model_unavailable",
        permanent=True,
        details={"models": list(missing)},
    )


def _evaluation_inputs(
    candidates: Recipe | Sequence[Recipe],
    benchmark: str | None,
    limit: int | None,
) -> tuple[Recipe, ...]:
    from screamingface._evaluation import _candidate_values, _validate_limit

    values = _candidate_values(candidates)
    if benchmark is not None and (not isinstance(benchmark, str) or not benchmark.strip()):
        raise ValueError("benchmark must be a non-empty string or None")
    _validate_limit(limit)
    return values


__all__ = ["AsyncClient", "Client", "DEFAULT_ENGINE_URL"]
