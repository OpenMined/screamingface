"""SF Engine REST + WebSocket Run lifecycle."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from websockets.asyncio import client as async_ws
from websockets.asyncio.client import ClientConnection as AsyncClientConnection
from websockets.exceptions import InvalidStatus, WebSocketException
from websockets.sync import client as sync_ws
from websockets.sync.connection import Connection as SyncConnection
from websockets.typing import Subprotocol

from screamingface._core.ports import _RunOutcome
from screamingface._core.wire import _REPLAY_SAFE
from screamingface._engine.access_contract import _challenge_audience
from screamingface._engine.auth import _default_caller_auth, _TransportAuth
from screamingface._engine.run_lifecycle import _Lifecycle
from screamingface._evaluation.model import Candidate
from screamingface.errors import AuthenticationError, EngineUnavailableError, ExecutionError
from screamingface.events import Event

type SyncEventCallback = Callable[[Event], None]
type AsyncEventCallback = Callable[[Event], None | Awaitable[None]]
_SUBPROTOCOL = Subprotocol("cloudevents.json")
_ATTACH_RETRY_DELAYS = (0.0, 0.01, 0.02, 0.04, 0.08, 0.16, 0.32)
_EVENT_RECEIVE_TIMEOUT_SECONDS = 120.0
# WHY: stopping happens while the caller is already interrupting. Inheriting the 30s client
# timeout would block Ctrl-C for half a minute per orphaned capability, and a user who waits
# that long presses Ctrl-C again — losing the very stop this exists to deliver.
_STOP_TIMEOUT_SECONDS = 5.0
# The Engine answers a stop for a Run it has already finished with one of these.
_ALREADY_STOPPED_STATUSES = frozenset({404, 409, 410})


class _SyncSender(Protocol):
    def send(self, message: str) -> None: ...


class _AsyncSender(Protocol):
    async def send(self, message: str) -> None: ...


class _ObserverRaised(Exception):
    """Protect a callback's original exception from transport error translation."""

    def __init__(self, original: BaseException) -> None:
        self.original = original


class Url4CloudTransport:
    """Synchronous adapter for the confirmed url4-cloud lifecycle."""

    def __init__(self, engine_url: str, caller_auth: _TransportAuth | None = None) -> None:
        self._engine_url = engine_url
        self._owns_auth = caller_auth is None
        self._caller_auth = caller_auth or _default_caller_auth(engine_url)
        self._http = httpx.Client(base_url=engine_url, timeout=30.0, auth=self._caller_auth)
        self._active_lock = Lock()
        self._active_tokens: set[str] = set()

    def run(
        self,
        candidate: Candidate,
        on_event: SyncEventCallback | None,
    ) -> _RunOutcome:
        token = _mint_sync(self._http)
        with self._active_lock:
            self._active_tokens.add(token)
        lifecycle = _Lifecycle(candidate)
        try:
            for attempt in range(2):
                try:
                    with sync_ws.connect(
                        _websocket_url(self._engine_url, token),
                        subprotocols=[_SUBPROTOCOL],
                        additional_headers=self._caller_auth.websocket_headers(),
                        open_timeout=30,
                        close_timeout=10,
                    ) as websocket:
                        return self._run_connected(
                            websocket,
                            lifecycle,
                            token,
                            candidate,
                            on_event,
                        )
                except InvalidStatus as exc:
                    if attempt != 0 or not _is_access_websocket_rejection(exc):
                        raise
                    self._caller_auth.reauthenticate()
            raise AssertionError("WebSocket authentication retry loop exhausted")
        except _ObserverRaised as exc:
            _copy_notes(exc, exc.original)
            raise exc.original
        except (WebSocketException, OSError, TimeoutError) as exc:
            raise _disconnected() from exc
        finally:
            with self._active_lock:
                self._active_tokens.discard(token)

    def cancel_active(self) -> None:
        """Stop every run currently owned by this synchronous Client."""

        with self._active_lock:
            tokens = tuple(self._active_tokens)
        if not tokens:
            return
        with ThreadPoolExecutor(
            max_workers=len(tokens),
            thread_name_prefix="screamingface-stop",
        ) as executor:
            futures = tuple(executor.submit(_stop_sync, self._http, token) for token in tokens)
        errors: list[Exception] = []
        for future in futures:
            error = future.exception()
            if isinstance(error, Exception):
                errors.append(error)
        if errors:
            raise ExceptionGroup("Could not stop every active SF Engine Run", errors)

    def _run_connected(
        self,
        websocket: SyncConnection,
        lifecycle: _Lifecycle,
        token: str,
        candidate: Candidate,
        on_event: SyncEventCallback | None,
    ) -> _RunOutcome:
        _require_subprotocol(websocket.subprotocol)
        websocket.send(lifecycle.initial_attach())
        try:
            _start_sync(self._http, token, candidate.url4)
            while True:
                try:
                    frame = websocket.recv(timeout=_EVENT_RECEIVE_TIMEOUT_SECONDS)
                except TimeoutError as exc:
                    raise _event_stream_timeout() from exc
                step = lifecycle.accept(frame)
                if step.command is not None:
                    websocket.send(step.command)
                    continue
                if step.event is not None and on_event is not None:
                    _observe_sync(on_event, step.event)
                if step.outcome is not None:
                    return step.outcome
        # WHY: interruption must stop otherwise-invisible paid work.
        except BaseException as exc:
            _record_stop_failure(exc, _try_send_sync(websocket, lifecycle.stop()))
            raise

    def close(self) -> None:
        try:
            self._http.close()
        finally:
            if self._owns_auth:
                self._caller_auth.close()


class AsyncUrl4CloudTransport:
    """Asynchronous adapter with the same lifecycle semantics.

    INVARIANT: one instance is driven by exactly one event loop — ``httpx.AsyncClient`` is
    loop-bound after first use — so ``_active_tokens`` needs no lock. Every read and write of
    it happens with no ``await`` in between, which makes the region atomic already; an
    ``asyncio.Lock`` would introduce the suspension points it is meant to protect against.
    AIDEV-NOTE: the asymmetry with the synchronous twin's ``threading.Lock`` is deliberate.
    That one is genuinely required, because a thread pool drives it.
    """

    def __init__(self, engine_url: str, caller_auth: _TransportAuth | None = None) -> None:
        self._engine_url = engine_url
        self._owns_auth = caller_auth is None
        self._caller_auth = caller_auth or _default_caller_auth(engine_url)
        self._http = httpx.AsyncClient(base_url=engine_url, timeout=30.0, auth=self._caller_auth)
        self._active_tokens: set[str] = set()

    async def cancel_active(self) -> None:
        """Stop every Run currently owned by this asynchronous Client."""

        tokens = tuple(self._active_tokens)
        if not tokens:
            return
        # Retiring them here bounds the registry: a cancelled Run deliberately leaves its
        # capability behind, and this sweep is what owns clearing it.
        self._active_tokens.clear()
        results = await asyncio.gather(
            *(_stop_async(self._http, token) for token in tokens),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        # INVARIANT: a CancelledError returned by gather is not an ordinary stop failure and
        # must not be reported as one — re-raise it so the interruption keeps propagating.
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result
        if errors:
            raise ExceptionGroup("Could not stop every active SF Engine Run", errors)

    async def run(
        self,
        candidate: Candidate,
        on_event: AsyncEventCallback | None,
    ) -> _RunOutcome:
        token = await _mint_async(self._http)
        self._active_tokens.add(token)
        cancelled = False
        try:
            return await self._connected_run(token, candidate, on_event)
        # WHY: a cancelled Run keeps its capability registered so the Evaluation's sweep can
        # still stop it. asyncio.gather cancels its children and only re-raises once they have
        # all unwound, so by the time the sweep runs every Run here has already finished its
        # own cleanup — retiring the capability on this path would hand the sweep an empty
        # registry and silently orphan paid work. The sweep clears what it stops.
        # AIDEV-NOTE: the synchronous twin does not need this. Its sibling worker threads are
        # still mid-Run when the sweep reads the registry.
        except asyncio.CancelledError:
            cancelled = True
            raise
        except _ObserverRaised as exc:
            _copy_notes(exc, exc.original)
            raise exc.original
        except (WebSocketException, OSError, TimeoutError) as exc:
            raise _disconnected() from exc
        finally:
            if not cancelled:
                self._active_tokens.discard(token)

    async def _connected_run(
        self,
        token: str,
        candidate: Candidate,
        on_event: AsyncEventCallback | None,
    ) -> _RunOutcome:
        lifecycle = _Lifecycle(candidate)
        for attempt in range(2):
            try:
                async with async_ws.connect(
                    _websocket_url(self._engine_url, token),
                    subprotocols=[_SUBPROTOCOL],
                    additional_headers=await self._caller_auth.websocket_headers_async(),
                    open_timeout=30,
                    close_timeout=10,
                ) as websocket:
                    return await self._run_connected(
                        websocket,
                        lifecycle,
                        token,
                        candidate,
                        on_event,
                    )
            except InvalidStatus as exc:
                if attempt != 0 or not _is_access_websocket_rejection(exc):
                    raise
                await self._caller_auth.reauthenticate_async()
        raise AssertionError("WebSocket authentication retry loop exhausted")

    async def _run_connected(
        self,
        websocket: AsyncClientConnection,
        lifecycle: _Lifecycle,
        token: str,
        candidate: Candidate,
        on_event: AsyncEventCallback | None,
    ) -> _RunOutcome:
        _require_subprotocol(websocket.subprotocol)
        await websocket.send(lifecycle.initial_attach())
        try:
            await _start_async(self._http, token, candidate.url4)
            while True:
                try:
                    frame = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=_EVENT_RECEIVE_TIMEOUT_SECONDS,
                    )
                except TimeoutError as exc:
                    raise _event_stream_timeout() from exc
                step = lifecycle.accept(frame)
                if step.command is not None:
                    await websocket.send(step.command)
                    continue
                if step.event is not None and on_event is not None:
                    await _observe_async(on_event, step.event)
                if step.outcome is not None:
                    return step.outcome
        # WHY: cancellation must stop otherwise-invisible paid work.
        except BaseException as exc:
            stop_error = await _try_send_async(websocket, lifecycle.stop())
            _record_stop_failure(exc, stop_error)
            raise

    async def close(self) -> None:
        try:
            await self._http.aclose()
        finally:
            if self._owns_auth:
                await asyncio.to_thread(self._caller_auth.close)


def _observe_sync(callback: SyncEventCallback, event: Event) -> None:
    try:
        callback(event)
    # WHY: preserve arbitrary application callback errors and interruptions without translation.
    except BaseException as exc:
        raise _ObserverRaised(exc) from exc


async def _observe_async(callback: AsyncEventCallback, event: Event) -> None:
    try:
        returned = callback(event)
        if inspect.isawaitable(returned):
            await returned
    # WHY: preserve arbitrary application callback errors and cancellation without translation.
    except BaseException as exc:
        raise _ObserverRaised(exc) from exc


def _event_stream_timeout() -> ExecutionError:
    return ExecutionError(
        "SF Engine Run event stream stopped responding",
        code="event_stream_timeout",
        permanent=False,
    )


def _mint_sync(http: httpx.Client) -> str:
    try:
        response = http.post("/token", extensions={_REPLAY_SAFE: True})
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not reach the SF Engine capability endpoint",
            engine_url=_http_origin(http),
        ) from exc
    return _token(response)


async def _mint_async(http: httpx.AsyncClient) -> str:
    try:
        response = await http.post("/token", extensions={_REPLAY_SAFE: True})
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not reach the SF Engine capability endpoint",
            engine_url=_http_origin(http),
        ) from exc
    return _token(response)


def _token(response: httpx.Response) -> str:
    _require_success(response, "mint an execution capability")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ExecutionError("SF Engine capability response must be JSON") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"token"}
        or not isinstance(payload["token"], str)
        or not payload["token"].strip()
    ):
        raise ExecutionError("SF Engine capability response is malformed")
    return payload["token"].strip()


def _start_sync(http: httpx.Client, token: str, url4: str) -> None:
    for delay in _ATTACH_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            response = http.get(
                "/",
                params={"q": url4},
                headers={"URL4-Capability": token, "Prefer": "respond-async"},
            )
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(
                "Could not start the SF Engine Run",
                engine_url=_http_origin(http),
            ) from exc
        if not _attachment_is_still_registering(response):
            break
    _accepted(response)


def _stop_sync(http: httpx.Client, token: str) -> None:
    try:
        response = http.delete(
            "/",
            headers={"URL4-Capability": token},
            extensions={_REPLAY_SAFE: True},
            timeout=_STOP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not stop the SF Engine Run",
            engine_url=_http_origin(http),
        ) from exc
    _require_stopped(response)


async def _stop_async(http: httpx.AsyncClient, token: str) -> None:
    try:
        response = await http.delete(
            "/",
            headers={"URL4-Capability": token},
            extensions={_REPLAY_SAFE: True},
            timeout=_STOP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not stop the SF Engine Run",
            engine_url=_http_origin(http),
        ) from exc
    _require_stopped(response)


def _require_stopped(response: httpx.Response) -> None:
    """Treat an already-finished Run as a stopped Run.

    WHY: the in-band ai.url4.stop frame usually wins the race, so this REST fallback
    routinely arrives after the Run is already gone. "It is not running" is the outcome the
    caller asked for, not an error worth attaching to their interruption.
    """

    if response.status_code in _ALREADY_STOPPED_STATUSES:
        return
    _require_success(response, "stop the Run")


async def _start_async(http: httpx.AsyncClient, token: str, url4: str) -> None:
    for delay in _ATTACH_RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            response = await http.get(
                "/",
                params={"q": url4},
                headers={"URL4-Capability": token, "Prefer": "respond-async"},
            )
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(
                "Could not start the SF Engine Run",
                engine_url=_http_origin(http),
            ) from exc
        if not _attachment_is_still_registering(response):
            break
    _accepted(response)


def _attachment_is_still_registering(response: httpx.Response) -> bool:
    media_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
    if response.status_code != 428 or media_type != "application/problem+json":
        return False
    try:
        problem = response.json()
    except ValueError:
        return False
    detail = problem.get("detail") if isinstance(problem, dict) else None
    return isinstance(detail, str) and "attach a websocket" in detail.casefold()


def _accepted(response: httpx.Response) -> None:
    if response.status_code != 202:
        _raise_response(response, "start the Run")
    if response.headers.get("Preference-Applied") != "respond-async":
        raise ExecutionError("SF Engine did not acknowledge asynchronous execution")
    if not response.headers.get("Location"):
        raise ExecutionError("SF Engine asynchronous response is missing Location")


def _require_success(response: httpx.Response, operation: str) -> None:
    if not response.is_success:
        _raise_response(response, operation)


def _raise_response(response: httpx.Response, operation: str) -> None:
    code: str | None = None
    problem: object = None
    detail = response.text.strip() or f"HTTP {response.status_code}"
    media_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
    if media_type == "application/problem+json":
        try:
            problem = response.json()
        except ValueError:
            problem = None
        if isinstance(problem, dict):
            if isinstance(problem.get("detail"), str):
                detail = problem["detail"]
            if isinstance(problem.get("type"), str):
                code = problem["type"]
    exception = AuthenticationError if response.status_code in {401, 403} else ExecutionError
    if exception is AuthenticationError:
        raise AuthenticationError(
            f"Could not {operation}: {detail}",
            code=code,
            status=response.status_code,
            permanent=True,
            details=problem if media_type == "application/problem+json" else None,
        )
    raise ExecutionError(
        f"Could not {operation}: {detail}",
        code=code,
        status=response.status_code,
        permanent=response.status_code < 500,
        details=problem if media_type == "application/problem+json" else None,
    )


def _websocket_url(engine_url: str, token: str) -> str:
    parts = urlsplit(engine_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/ws", urlencode({"ticket": token}), ""))


def _http_origin(http: httpx.Client | httpx.AsyncClient) -> str:
    return str(http.base_url).rstrip("/")


def _is_access_websocket_rejection(error: InvalidStatus) -> bool:
    # WHY: one predicate for all three call sites. This path used to accept a Location
    # carrying TWO kid parameters while the HTTP path required exactly one, and skipped the
    # audience-format check entirely.
    response = error.response
    return _challenge_audience(response.status_code, response.headers) is not None


def _require_subprotocol(selected: str | None) -> None:
    if selected != _SUBPROTOCOL:
        raise ExecutionError("SF Engine WebSocket did not negotiate cloudevents.json")


def _try_send_sync(websocket: _SyncSender, command: str) -> Exception | None:
    try:
        websocket.send(command)
    except (WebSocketException, OSError, RuntimeError) as exc:
        return exc
    return None


async def _try_send_async(websocket: _AsyncSender, command: str) -> Exception | None:
    try:
        await websocket.send(command)
    except (WebSocketException, OSError, RuntimeError) as exc:
        return exc
    return None


def _record_stop_failure(original: BaseException, stop_error: Exception | None) -> None:
    if stop_error is not None:
        original.add_note(f"SF Engine stop request also failed: {stop_error}")


def _copy_notes(source: BaseException, target: BaseException) -> None:
    for note in getattr(source, "__notes__", ()):
        target.add_note(note)


def _disconnected() -> ExecutionError:
    return ExecutionError(
        "SF Engine WebSocket disconnected before the Run completed",
        code="websocket_disconnected",
        permanent=False,
    )


__all__: list[str] = []
