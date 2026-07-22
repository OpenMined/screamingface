"""Raw-ASGI private connection control plane owned by ScreamingFace engine."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any
from urllib.parse import parse_qs

from screamingface_engine.catalog import PROVIDER_ROUTES
from screamingface_engine.connection_contract import (
    ConnectionControlError,
    parse_unique_json_object,
)
from screamingface_engine.connection_manager import ConnectionManager

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]

MAX_CONNECTION_BODY_BYTES = 16_384
CALLBACK_PATHS = frozenset(
    provider.callback_path for provider in PROVIDER_ROUTES if provider.callback_path is not None
)
_CALLBACK_SUCCESS = """<!doctype html>
<html><body><p>Authentication complete. You may close this window.</p></body></html>
"""
_CALLBACK_FAILURE = """<!doctype html>
<html><body><p>Authentication failed. Return to ScreamingFace and try again.</p></body></html>
"""


class ConnectionASGI:
    """Intercept connection control and OAuth browser callbacks before URL4 dispatch."""

    def __init__(self, connections: ConnectionManager) -> None:
        self._connections = connections

    @staticmethod
    def handles(scope: Mapping[str, Any]) -> bool:
        path = str(scope.get("path", ""))
        return (
            path == "/v1/connections"
            or path.startswith("/v1/connections/")
            or path in CALLBACK_PATHS
        )

    async def __call__(self, scope: Mapping[str, Any], receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()
        try:
            if path in CALLBACK_PATHS:
                await self._callback(path, method, scope, send)
                return
            await self._control(path, method, scope, receive, send)
        except ConnectionControlError as exc:
            await _send_error(send, exc)

    async def _control(
        self,
        path: str,
        method: str,
        scope: Mapping[str, Any],
        receive: Receive,
        send: Send,
    ) -> None:
        if path == "/v1/connections":
            _require_method(method, {"GET"})
            await _send_json(send, 200, await self._connections.list_public())
            return
        parts = path.removeprefix("/v1/connections/").split("/")
        provider = self._connections.provider(parts[0])
        if len(parts) == 1:
            if method == "GET":
                await _send_json(send, 200, await self._connections.get_public(provider))
            elif method == "DELETE":
                await self._connections.disconnect(provider)
                await _send_empty(send, 204)
            else:
                _method_not_allowed()
            return
        if parts[1:] == ["oauth"]:
            _require_method(method, {"POST"})
            await _require_empty_body(scope, receive)
            await _send_json(send, 200, await self._connections.start_oauth(provider))
            return
        if parts[1:] == ["api-key"]:
            _require_method(method, {"PUT"})
            api_key = await _api_key(scope, receive, provider.id)
            await _send_json(send, 200, await self._connections.set_api_key(provider, api_key))
            return
        raise ConnectionControlError(
            404,
            "unknown_connection_route",
            "Unknown provider connection route.",
            provider=provider.id,
        )

    async def _callback(
        self,
        path: str,
        method: str,
        scope: Mapping[str, Any],
        send: Send,
    ) -> None:
        if method != "GET":
            await _send_html(send, 405, _CALLBACK_FAILURE)
            return
        query = scope.get("query_string", b"")
        if not isinstance(query, bytes):
            await _send_html(send, 400, _CALLBACK_FAILURE)
            return
        try:
            values = parse_qs(query.decode("ascii"), keep_blank_values=True)
            code = _single_query(values, "code")
            state = _single_query(values, "state")
            await self._connections.complete_callback(path, code, state)
        except ConnectionControlError as exc:
            await _send_html(send, exc.status, _CALLBACK_FAILURE)
            return
        except (UnicodeDecodeError, ValueError):
            await _send_html(send, 400, _CALLBACK_FAILURE)
            return
        await _send_html(send, 200, _CALLBACK_SUCCESS)

    async def aclose(self) -> None:
        await self._connections.aclose()


async def _api_key(scope: Mapping[str, Any], receive: Receive, provider: str) -> str:
    if _content_type(scope) != "application/json":
        raise ConnectionControlError(
            415,
            "invalid_api_key",
            "API keys require an application/json request body.",
            provider=provider,
        )
    body = await _read_body(scope, receive, provider)
    try:
        payload = parse_unique_json_object(body.decode("utf-8"))
        if set(payload) != {"api_key"}:
            raise ValueError("expected only api_key")
        api_key = payload["api_key"]
        if not isinstance(api_key, str) or len(api_key.strip()) < 8:
            raise ValueError("api_key is missing or too short")
        return api_key.strip()
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise ConnectionControlError(
            400,
            "invalid_api_key",
            "The API key request is invalid.",
            provider=provider,
        ) from exc


async def _require_empty_body(scope: Mapping[str, Any], receive: Receive) -> None:
    body = await _read_body(scope, receive, None)
    if body:
        raise ConnectionControlError(
            400,
            "invalid_request",
            "This connection request does not accept a body.",
        )


async def _read_body(scope: Mapping[str, Any], receive: Receive, provider: str | None) -> bytes:
    declared = _content_length(scope)
    if declared is not None and declared > MAX_CONNECTION_BODY_BYTES:
        _body_too_large(provider)
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            continue
        chunk = message.get("body", b"")
        if not isinstance(chunk, bytes):
            raise ConnectionControlError(400, "invalid_request", "Invalid HTTP request body.")
        size += len(chunk)
        if size > MAX_CONNECTION_BODY_BYTES:
            _body_too_large(provider)
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


def _body_too_large(provider: str | None) -> None:
    raise ConnectionControlError(
        413,
        "request_body_too_large",
        f"Connection request bodies are limited to {MAX_CONNECTION_BODY_BYTES} bytes.",
        provider=provider,
    )


def _content_type(scope: Mapping[str, Any]) -> str | None:
    value = _header(scope, b"content-type")
    return value.split(";", 1)[0].strip().lower() if value else None


def _content_length(scope: Mapping[str, Any]) -> int | None:
    value = _header(scope, b"content-length")
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConnectionControlError(400, "invalid_request", "Invalid Content-Length.") from exc
    if parsed < 0:
        raise ConnectionControlError(400, "invalid_request", "Invalid Content-Length.")
    return parsed


def _header(scope: Mapping[str, Any], name: bytes) -> str | None:
    headers = scope.get("headers", ())
    if not isinstance(headers, (list, tuple)):
        return None
    values = [
        value.decode("latin-1")
        for key, value in headers
        if isinstance(key, bytes) and isinstance(value, bytes) and key.lower() == name
    ]
    if len(values) > 1:
        raise ConnectionControlError(400, "invalid_request", "Duplicate HTTP header.")
    return values[0] if values else None


def _single_query(values: dict[str, list[str]], name: str) -> str:
    selected = values.get(name, [])
    if len(selected) != 1 or not selected[0] or len(selected[0]) > 4096:
        raise ValueError(f"invalid OAuth {name}")
    return selected[0]


def _require_method(method: str, allowed: set[str]) -> None:
    if method not in allowed:
        _method_not_allowed()


def _method_not_allowed() -> None:
    raise ConnectionControlError(
        405,
        "method_not_allowed",
        "HTTP method is not allowed for this connection route.",
    )


async def _send_error(send: Send, error: ConnectionControlError) -> None:
    await _send_json(
        send,
        error.status,
        {
            "schema": "screamingface.error.v1",
            "code": error.code,
            "message": str(error),
            "provider": error.provider,
            "retryable": error.retryable,
        },
    )


async def _send_json(send: Send, status: int, payload: Mapping[str, object]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode()
    await _send_response(send, status, body, b"application/json")


async def _send_html(send: Send, status: int, body: str) -> None:
    await _send_response(send, status, body.encode(), b"text/html; charset=utf-8")


async def _send_empty(send: Send, status: int) -> None:
    await _send_response(send, status, b"", None)


async def _send_response(send: Send, status: int, body: bytes, content_type: bytes | None) -> None:
    headers = [(b"content-length", str(len(body)).encode())]
    if content_type is not None:
        headers.append((b"content-type", content_type))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


__all__ = ["CALLBACK_PATHS", "ConnectionASGI", "MAX_CONNECTION_BODY_BYTES"]
