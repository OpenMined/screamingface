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

    from screamingface._core.ports import AsyncRunTransport, SyncRunTransport
    from screamingface._engine.catalog import AsyncBenchmarks, AsyncModels, Benchmarks, Models
    from screamingface._engine.connections import AsyncConnections, Connections
    from screamingface._ui.connections import ConnectionPanel
    from screamingface.connections import Connection
    from screamingface.events import Event
    from screamingface.recipe import Recipe
    from screamingface.report import Report

DEFAULT_ENGINE_URL = "http://127.0.0.1:9108"


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

    def __init__(
        self,
        *,
        engine_url: str = DEFAULT_ENGINE_URL,
        http_transport: httpx.BaseTransport | None = None,
        run_transport: SyncRunTransport | None = None,
    ) -> None:
        import httpx

        from screamingface._engine.auth import _default_caller_auth
        from screamingface._engine.benchmark import BenchmarkResources
        from screamingface._engine.catalog import Benchmarks, Models
        from screamingface._engine.connections import Connections
        from screamingface._engine.transport import Url4CloudTransport

        self._engine_url = _engine_origin(engine_url)
        self._closed = False
        self._auth_listeners = _AuthListeners()
        self._auth = _default_caller_auth(self._engine_url)
        self._http = httpx.Client(
            base_url=self._engine_url,
            timeout=30.0,
            auth=self._auth,
            transport=http_transport,
        )
        self._transport: SyncRunTransport = (
            run_transport
            if run_transport is not None
            else Url4CloudTransport(self._engine_url, self._auth)
        )
        self.models: Models = Models(self._http_get, self._engine_url)
        self.benchmarks: Benchmarks = Benchmarks(self._http_get, self._engine_url)
        self._benchmark_resources = BenchmarkResources(self._http)
        self.connections: Connections = Connections(self._http_request, self._engine_url)

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

        from screamingface._evaluation.runner import evaluate_sync

        self._require_open()
        return evaluate_sync(
            self._benchmark_resources.load,
            self._transport,
            self.models.list,
            candidates,
            benchmark,
            limit,
            on_event,
            progress,
        )

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
            from screamingface._ui.connections import ConnectionPanel

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

    def __init__(
        self,
        *,
        engine_url: str = DEFAULT_ENGINE_URL,
        http_transport: httpx.AsyncBaseTransport | None = None,
        run_transport: AsyncRunTransport | None = None,
    ) -> None:
        import httpx

        from screamingface._engine.auth import _default_caller_auth
        from screamingface._engine.benchmark import AsyncBenchmarkResources
        from screamingface._engine.catalog import AsyncBenchmarks, AsyncModels
        from screamingface._engine.connections import AsyncConnections
        from screamingface._engine.transport import AsyncUrl4CloudTransport

        self._engine_url = _engine_origin(engine_url)
        self._closed = False
        self._auth_listeners = _AuthListeners()
        self._auth = _default_caller_auth(self._engine_url)
        self._http = httpx.AsyncClient(
            base_url=self._engine_url,
            timeout=30.0,
            auth=self._auth,
            transport=http_transport,
        )
        self._transport: AsyncRunTransport = (
            run_transport
            if run_transport is not None
            else AsyncUrl4CloudTransport(self._engine_url, self._auth)
        )
        self.models: AsyncModels = AsyncModels(self._http_get, self._engine_url)
        self.benchmarks: AsyncBenchmarks = AsyncBenchmarks(self._http_get, self._engine_url)
        self._benchmark_resources = AsyncBenchmarkResources(self._http)
        self.connections: AsyncConnections = AsyncConnections(self._http_request, self._engine_url)

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

        from screamingface._evaluation.runner import evaluate_async

        self._require_open()
        return await evaluate_async(
            self._benchmark_resources.load,
            self._transport,
            self.models.list,
            candidates,
            benchmark,
            limit,
            on_event,
            progress,
        )

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


__all__ = ["AsyncClient", "Client", "DEFAULT_ENGINE_URL"]
