"""Application-owned lifecycle, admission, and timeout wrapper for Url4Node."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from contextlib import suppress
from typing import Any

from url4 import Url4Node

from screamingface_engine.connection_asgi import ConnectionASGI
from screamingface_engine.docs import DocumentationASGI
from screamingface_engine.evaluation_events import evaluation_event_sink
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]
type AsgiApp = Callable[[Mapping[str, Any], Receive, Send], Awaitable[None]]
type NodeInitializer = Callable[[], Awaitable[Url4Node]]

_APPLICATION_ERROR_STATUSES = {
    "malformed_tool_policy": 400,
    "unsupported_tool": 400,
    "invalid_tool_request": 400,
    "authentication_required": 401,
    "dataset_authentication_required": 401,
    "payment_required": 402,
    "rate_limited": 429,
    "tool_budget_exhausted": 422,
    "provider_unavailable": 502,
    "invalid_provider_response": 502,
}
_EVALUATION_STREAM_SCHEMA = "screamingface.evaluation-event.v1"
_EVAL_PATH = "/v1"


class EngineASGI:
    """Add process-level concerns while leaving all URL4 dispatch to the node."""

    def __init__(
        self,
        node: Url4Node | None,
        gateway: GatewayClient,
        *,
        initialize: NodeInitializer | None = None,
        connections: ConnectionASGI | None = None,
        documentation: DocumentationASGI | None = None,
        max_inflight: int,
        timeout: float,
        max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
        stream_interval: float = 5.0,
    ) -> None:
        if node is None and initialize is None:
            raise ValueError("engine requires a node or startup initializer")
        self.node = node
        self.gateway = gateway
        self.connections = connections
        self.documentation = documentation
        self._base: AsgiApp | None = None if node is None else node.asgi()
        self._initialize = initialize
        self._max_inflight = max_inflight
        self._timeout = timeout
        self._max_request_target_bytes = max_request_target_bytes
        if stream_interval <= 0:
            raise ValueError("stream interval must be positive")
        self._stream_interval = stream_interval
        self._inflight = 0

    async def __call__(self, scope: Mapping[str, Any], receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
        elif scope["type"] == "http":
            await self._serve_http(scope, receive, send)
        else:  # pragma: no cover - the engine exposes no websocket surface
            base = self._base
            if base is None:
                raise RuntimeError("engine startup is incomplete")
            await base(scope, receive, send)

    async def _serve_http(self, scope: Mapping[str, Any], receive: Receive, send: Send) -> None:
        if _request_target_bytes(scope) > self._max_request_target_bytes:
            await _send_error(
                send,
                414,
                "request_target_too_large",
                f"request target exceeds {self._max_request_target_bytes} bytes",
            )
            return
        if self.documentation is not None and self.documentation.handles(scope):
            await self.documentation(scope, receive, send)
            return
        if self._base is None:
            await _send_error(send, 503, "not_ready", "engine startup is incomplete")
            return
        if self.connections is not None and self.connections.handles(scope):
            await self.connections(scope, receive, send)
            return
        if self._inflight >= self._max_inflight:
            await _send_error(
                send,
                503,
                "overloaded",
                "server at capacity, retry shortly",
                retry=True,
            )
            return
        self._inflight += 1
        try:
            if _requests_evaluation_stream(scope):
                await self._serve_evaluation_stream(scope, receive, send)
            else:
                guard = _StartGuard(send)
                application_errors = _ApplicationErrorGuard(guard.send)
                try:
                    async with asyncio.timeout(self._timeout):
                        await self._base(scope, receive, application_errors.send)
                except TimeoutError:
                    if not guard.started:
                        await _send_error(
                            send,
                            504,
                            "timeout",
                            f"evaluation exceeded {self._timeout}s",
                        )
        finally:
            self._inflight -= 1

    async def _serve_evaluation_stream(
        self, scope: Mapping[str, Any], receive: Receive, send: Send
    ) -> None:
        """Stream honest lifecycle events around one unchanged URL4 evaluation."""

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/event-stream; charset=utf-8"),
                    (b"cache-control", b"no-cache"),
                    (b"x-accel-buffering", b"no"),
                ],
            }
        )
        await _send_stream_event(send, "accepted")
        try:
            collector = await self._collect_evaluation(scope, receive, send)
            value = _stream_value(collector)
        except TimeoutError:
            await _send_stream_error(
                send,
                504,
                "timeout",
                f"evaluation exceeded {self._timeout}s",
            )
        except _StreamFailure as exc:
            await _send_stream_error(send, exc.status, exc.code, exc.message)
        except Exception:
            await _send_stream_error(
                send,
                500,
                "internal_error",
                "evaluation failed unexpectedly",
            )
        else:
            await _send_stream_event(
                send,
                "complete",
                content_type="text/plain",
                value=value,
            )
        await _end_stream(send)

    async def _collect_evaluation(
        self, scope: Mapping[str, Any], receive: Receive, send: Send
    ) -> _BufferedResponse:
        started = asyncio.get_running_loop().time()
        collector = _BufferedResponse()
        application_errors = _ApplicationErrorGuard(collector.send)
        events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        base = self._base
        if base is None:  # pragma: no cover - checked by _serve_http
            raise RuntimeError("engine startup is incomplete")
        with evaluation_event_sink(events.put_nowait):
            evaluation = asyncio.ensure_future(base(scope, receive, application_errors.send))
        event_waiter = asyncio.create_task(events.get())
        try:
            async with asyncio.timeout(self._timeout):
                while True:
                    done, _ = await asyncio.wait(
                        {evaluation, event_waiter},
                        timeout=self._stream_interval,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if event_waiter in done:
                        await _send_stream_event(send, "progress", **event_waiter.result())
                        event_waiter = asyncio.create_task(events.get())
                    if evaluation in done:
                        break
                    if not done:
                        elapsed = round(asyncio.get_running_loop().time() - started, 1)
                        await _send_stream_event(send, "running", elapsed_seconds=elapsed)
                await evaluation
                await asyncio.sleep(0)
                if event_waiter.done():
                    await _send_stream_event(send, "progress", **event_waiter.result())
                else:
                    event_waiter.cancel()
                    with suppress(asyncio.CancelledError):
                        await event_waiter
                while not events.empty():
                    await _send_stream_event(send, "progress", **events.get_nowait())
        finally:
            if not evaluation.done():
                evaluation.cancel()
                with suppress(asyncio.CancelledError):
                    await evaluation
            if not event_waiter.done():
                event_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await event_waiter
        return collector

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self._startup()
                except Exception as exc:
                    await self._close_adapters()
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                else:
                    await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self._close_adapters()
                if self.node is not None:
                    await self.node.aclose()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _startup(self) -> None:
        await self.gateway.start()
        if self.node is not None:
            return
        if self._initialize is None:  # pragma: no cover - constructor invariant
            raise RuntimeError("engine startup initializer is missing")
        node = await self._initialize()
        self.node = node
        self._base = node.asgi()

    async def _close_adapters(self) -> None:
        if self.connections is not None:
            await self.connections.aclose()
        await self.gateway.aclose()


class _StartGuard:
    def __init__(self, send: Send) -> None:
        self._send = send
        self.started = False

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.started = True
        await self._send(message)


class _ApplicationErrorGuard:
    """Translate application error codes without changing generic URL4."""

    def __init__(self, send: Send) -> None:
        self._send = send
        self._start: Message | None = None
        self._body = bytearray()

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            status = message.get("status")
            if isinstance(status, int) and status >= 400:
                self._start = dict(message)
                return
            await self._send(message)
            return
        if self._start is None:
            await self._send(message)
            return
        body = message.get("body", b"")
        if isinstance(body, bytes):
            self._body.extend(body)
        if message.get("more_body", False):
            return
        start = self._start
        start["status"] = _application_error_status(bytes(self._body), start["status"])
        await self._send(start)
        await self._send({"type": "http.response.body", "body": bytes(self._body)})


class _BufferedResponse:
    """Collect the unchanged Url4Node response behind an SSE envelope."""

    def __init__(self) -> None:
        self.status: int | None = None
        self.headers: list[tuple[bytes, bytes]] = []
        self.body = bytearray()

    @property
    def content_type(self) -> str:
        for name, value in self.headers:
            if name.lower() == b"content-type":
                return value.decode("latin-1").split(";", 1)[0].strip().lower()
        return ""

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            status = message.get("status")
            if not isinstance(status, int):
                raise RuntimeError("URL4 response has no status")
            self.status = status
            self.headers = list(message.get("headers", []))
            return
        body = message.get("body", b"")
        if isinstance(body, bytes):
            self.body.extend(body)


class _StreamFailure(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _application_error_status(body: bytes, fallback: object) -> int:
    status = fallback if isinstance(fallback, int) else 500
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return status
    if not isinstance(payload, Mapping):
        return status
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return status
    code = error.get("code")
    return _APPLICATION_ERROR_STATUSES.get(code, status) if isinstance(code, str) else status


def _request_target_bytes(scope: Mapping[str, Any]) -> int:
    raw_path = scope.get("raw_path")
    if not isinstance(raw_path, bytes):
        raw_path = str(scope.get("path", "")).encode("utf-8")
    query = scope.get("query_string", b"")
    if not isinstance(query, bytes):
        query = bytes(query)
    return len(raw_path) + (1 + len(query) if query else 0)


def _requests_evaluation_stream(scope: Mapping[str, Any]) -> bool:
    if scope.get("path") != _EVAL_PATH or scope.get("method") != "GET":
        return False
    for name, value in scope.get("headers", []):
        if name.lower() != b"accept":
            continue
        media_types = value.decode("latin-1").lower().split(",")
        if any(item.split(";", 1)[0].strip() == "text/event-stream" for item in media_types):
            return True
    return False


def _stream_error_details(body: bytes, status: int) -> tuple[str, str]:
    try:
        payload = json.loads(body)
        error = payload["error"]
        code = error["code"]
        message = error["message"]
        if isinstance(code, str) and code and isinstance(message, str) and message:
            return code, message
    except (KeyError, TypeError, UnicodeDecodeError, ValueError):
        pass
    return "evaluation_failed", f"URL4 evaluation returned HTTP {status}"


def _stream_value(response: _BufferedResponse) -> str:
    status = response.status
    if status is None:
        raise _StreamFailure(
            500,
            "invalid_engine_response",
            "URL4 evaluation produced no HTTP response",
        )
    if status >= 400:
        code, message = _stream_error_details(bytes(response.body), status)
        raise _StreamFailure(status, code, message)
    if response.content_type != "text/plain":
        raise _StreamFailure(
            500,
            "invalid_engine_response",
            "URL4 evaluation success was not plaintext",
        )
    try:
        return bytes(response.body).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _StreamFailure(
            500,
            "invalid_engine_response",
            "URL4 evaluation success was not UTF-8",
        ) from exc


async def _send_stream_event(send: Send, event: str, **fields: object) -> None:
    payload = json.dumps(
        {"schema": _EVALUATION_STREAM_SCHEMA, "type": event, **fields},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    body = f"event: {event}\ndata: {payload}\n\n".encode()
    await send({"type": "http.response.body", "body": body, "more_body": True})


async def _send_stream_error(send: Send, status: int, code: str, message: str) -> None:
    await _send_stream_event(
        send,
        "error",
        status=status,
        error={"code": code, "message": message},
    )


async def _end_stream(send: Send) -> None:
    await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _send_error(
    send: Send, status: int, code: str, message: str, *, retry: bool = False
) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    headers = [(b"content-type", b"application/json")]
    if retry:
        headers.append((b"retry-after", b"1"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


__all__ = ["EngineASGI"]
