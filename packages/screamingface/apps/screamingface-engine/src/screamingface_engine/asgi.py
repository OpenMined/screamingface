"""Application-owned lifecycle, admission, and timeout wrapper for Url4Node."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from url4 import Url4Node

from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES
from screamingface_engine.web_research import WebResearchClient

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]
type AsgiApp = Callable[[Mapping[str, Any], Receive, Send], Awaitable[None]]


class EngineASGI:
    """Add process-level concerns while leaving all URL4 dispatch to the node."""

    def __init__(
        self,
        node: Url4Node,
        gateway: GatewayClient,
        *,
        research: WebResearchClient | None = None,
        max_inflight: int,
        timeout: float,
        max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
    ) -> None:
        self.node = node
        self.gateway = gateway
        self.research = research
        self._base: AsgiApp = node.asgi()
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
            await self._base(scope, receive, send)

    async def _serve_http(self, scope: Mapping[str, Any], receive: Receive, send: Send) -> None:
        if _request_target_bytes(scope) > self._max_request_target_bytes:
            await _send_error(
                send,
                414,
                "request_target_too_large",
                f"request target exceeds {self._max_request_target_bytes} bytes",
            )
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
        try:
            async with asyncio.timeout(self._timeout):
                await self._base(scope, receive, guard.send)
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
                    await self.gateway.start()
                    if self.research is not None:
                        await self.research.start()
                except Exception as exc:
                    if self.research is not None:
                        await self.research.aclose()
                    await self.gateway.aclose()
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                else:
                    await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if self.research is not None:
                    await self.research.aclose()
                await self.gateway.aclose()
                await self.node.aclose()
                await send({"type": "lifespan.shutdown.complete"})
                return


class _StartGuard:
    def __init__(self, send: Send) -> None:
        self._send = send
        self.started = False

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.started = True
        await self._send(message)


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
