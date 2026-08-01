"""SF Engine REST + WebSocket Run lifecycle."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from websockets.asyncio import client as async_ws
from websockets.asyncio.client import ClientConnection as AsyncClientConnection
from websockets.exceptions import InvalidStatus, WebSocketException
from websockets.sync import client as sync_ws
from websockets.sync.connection import Connection as SyncConnection
from websockets.typing import Subprotocol

from screamingface._authentication import _CallerAuth, _default_caller_auth
from screamingface._engine_contract import _RunState
from screamingface._evaluation import Candidate
from screamingface._ports import _RunOutcome
from screamingface.errors import AuthenticationError, EngineUnavailableError, ExecutionError
from screamingface.events import Event

type SyncEventCallback = Callable[[Event], None]
type AsyncEventCallback = Callable[[Event], None | Awaitable[None]]
_SUBPROTOCOL = Subprotocol("cloudevents.json")


class _SyncSender(Protocol):
    def send(self, message: str) -> None: ...


class _AsyncSender(Protocol):
    async def send(self, message: str) -> None: ...


class _ObserverRaised(Exception):
    """Protect a callback's original exception from transport error translation."""

    def __init__(self, original: BaseException) -> None:
        self.original = original


@dataclass(frozen=True, slots=True)
class _LifecycleStep:
    command: str | None = None
    event: Event | None = None
    outcome: _RunOutcome | None = None


class _Lifecycle:
    """Shared protocol decisions; adapters provide only synchronous/asynchronous I/O."""

    def __init__(self, candidate: Candidate) -> None:
        self._state = _RunState(candidate.url4)

    @staticmethod
    def initial_attach() -> str:
        return _attach(None)

    @staticmethod
    def stop() -> str:
        return _stop("client stopped consuming events")

    def accept(self, frame: str | bytes) -> _LifecycleStep:
        accepted = self._state.accept(frame)
        command = None if accepted.replay_from is None else _attach(accepted.replay_from)
        return _LifecycleStep(
            command=command,
            event=accepted.event,
            outcome=accepted.outcome,
        )


class Url4CloudTransport:
    """Synchronous adapter for the confirmed url4-cloud lifecycle."""

    def __init__(self, engine_url: str, caller_auth: _CallerAuth | None = None) -> None:
        self._engine_url = engine_url
        self._owns_auth = caller_auth is None
        self._caller_auth = caller_auth or _default_caller_auth(engine_url)
        self._http = httpx.Client(base_url=engine_url, timeout=30.0, auth=self._caller_auth)

    def run(
        self,
        candidate: Candidate,
        on_event: SyncEventCallback | None,
    ) -> _RunOutcome:
        token = _mint_sync(self._http)
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
                step = lifecycle.accept(websocket.recv())
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
    """Asynchronous adapter with the same lifecycle semantics."""

    def __init__(self, engine_url: str, caller_auth: _CallerAuth | None = None) -> None:
        self._engine_url = engine_url
        self._owns_auth = caller_auth is None
        self._caller_auth = caller_auth or _default_caller_auth(engine_url)
        self._http = httpx.AsyncClient(base_url=engine_url, timeout=30.0, auth=self._caller_auth)

    async def run(
        self,
        candidate: Candidate,
        on_event: AsyncEventCallback | None,
    ) -> _RunOutcome:
        token = await _mint_async(self._http)
        lifecycle = _Lifecycle(candidate)
        try:
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
        except _ObserverRaised as exc:
            _copy_notes(exc, exc.original)
            raise exc.original
        except (WebSocketException, OSError, TimeoutError) as exc:
            raise _disconnected() from exc

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
                step = lifecycle.accept(await websocket.recv())
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


def _mint_sync(http: httpx.Client) -> str:
    try:
        response = http.post("/token")
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not reach the SF Engine capability endpoint",
            engine_url=_http_origin(http),
        ) from exc
    return _token(response)


async def _mint_async(http: httpx.AsyncClient) -> str:
    try:
        response = await http.post("/token")
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
    _accepted(response)


async def _start_async(http: httpx.AsyncClient, token: str, url4: str) -> None:
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
    _accepted(response)


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
    response = error.response
    if response.status_code not in {302, 401, 403}:
        return False
    if response.headers.get("cf-access-aud"):
        return True
    location = response.headers.get("location")
    return bool(location and parse_qs(urlsplit(location).query).get("kid"))


def _require_subprotocol(selected: str | None) -> None:
    if selected != _SUBPROTOCOL:
        raise ExecutionError("SF Engine WebSocket did not negotiate cloudevents.json")


def _attach(from_sequence: int | None) -> str:
    return _command("ai.url4.attach", {"from_sequence": from_sequence})


def _stop(reason: str) -> str:
    return _command("ai.url4.stop", {"reason": reason})


def _command(kind: str, data: dict[str, object]) -> str:
    return json.dumps(
        {
            "specversion": "1.0",
            "id": uuid4().hex,
            "source": "/screamingface/client",
            "time": datetime.now(UTC).isoformat(),
            "type": kind,
            "datacontenttype": "application/json",
            "data": data,
        },
        separators=(",", ":"),
    )


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
