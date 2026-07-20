"""Application-owned lifecycle, admission, and timeout wrapper for Url4Node."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from url4 import Url4Node

from screamingface_engine.connection_asgi import ConnectionASGI
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
    "rate_limited": 429,
    "tool_budget_exhausted": 422,
    "provider_unavailable": 502,
    "invalid_provider_response": 502,
}


class EngineASGI:
    """Add process-level concerns while leaving all URL4 dispatch to the node."""

    def __init__(
        self,
        node: Url4Node | None,
        gateway: GatewayClient,
        *,
        initialize: NodeInitializer | None = None,
        connections: ConnectionASGI | None = None,
        max_inflight: int,
        timeout: float,
        max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
    ) -> None:
        if node is None and initialize is None:
            raise ValueError("engine requires a node or startup initializer")
        self.node = node
        self.gateway = gateway
        self.connections = connections
        self._base: AsgiApp | None = None if node is None else node.asgi()
        self._initialize = initialize
        self._max_inflight = max_inflight
        self._timeout = timeout
        self._max_request_target_bytes = max_request_target_bytes
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
