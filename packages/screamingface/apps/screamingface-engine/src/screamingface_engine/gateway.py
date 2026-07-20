"""In-process adapter from URL4 model requests to the shared AI Gateway."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

import httpx
from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute

_ALLOWED_PARAMS = frozenset({"temperature", "max_tokens", "reasoning"})
_REASONING_VALUES = frozenset({"low", "medium", "high"})


class GatewayResponseTooLargeError(Exception):
    """An internal Gateway response exceeded its caller's explicit byte budget."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str

    def to_message(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(frozen=True, slots=True)
class AssistantTurn:
    content: str | None
    tool_calls: tuple[ToolCall, ...]

    def to_message(self) -> dict[str, object]:
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [tool_call.to_message() for tool_call in self.tool_calls],
        }


class GatewayClient:
    """One reusable asynchronous client shared by every registered model route."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def start(self) -> None:
        await self._get_client()

    async def aclose(self) -> None:
        async with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            await client.aclose()

    async def complete(self, model: ModelRoute, request: Request) -> str:
        turn = await self.turn(
            model,
            messages=_request_messages(request),
            params=request.params,
            tools=(),
        )
        if turn.content is None:
            raise ResolutionError(f"AI Gateway response has no text content for {model.id!r}")
        return turn.content

    async def turn(
        self,
        model: ModelRoute,
        *,
        messages: list[dict[str, object]],
        params: Mapping[str, str],
        tools: tuple[dict[str, object], ...],
    ) -> AssistantTurn:
        body = _turn_body(model, messages=messages, params=params, tools=tools)
        try:
            response = await self.request(
                "POST",
                "/v1/chat/completions",
                json=body,
                headers={"X-Profile": "default"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ResolutionError(f"AI Gateway timed out while running {model.id!r}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"AI Gateway returned HTTP {status} for {model.id!r}"
            if status == 401:
                raise ResolutionError(message, code="connection_needs_reauth") from exc
            if status == 403:
                raise ResolutionError(message, code="provider_access_denied") from exc
            raise ResolutionError(message) from exc
        except httpx.RequestError as exc:
            raise ResolutionError(f"AI Gateway request failed for {model.id!r}: {exc}") from exc
        return _response_turn(response, model)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        """Send one bounded internal request through the shared Gateway client."""

        client = await self._get_client()
        if max_response_bytes is None:
            return await client.request(method, path, params=params, json=json, headers=headers)
        request = client.build_request(method, path, params=params, json=json, headers=headers)
        response = await client.send(request, stream=True)
        chunks: list[bytes] = []
        size = 0
        try:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_response_bytes:
                    raise GatewayResponseTooLargeError(
                        f"Gateway response exceeded {max_response_bytes} bytes"
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=b"".join(chunks),
            request=request,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout,
                    transport=self._transport,
                )
            return self._client


def _request_messages(request: Request) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    if request.intent:
        messages.append({"role": "system", "content": request.intent})
    messages.append({"role": "user", "content": request.context})
    return messages


def _turn_body(
    model: ModelRoute,
    *,
    messages: list[dict[str, object]],
    params: Mapping[str, str],
    tools: tuple[dict[str, object], ...],
) -> dict[str, object]:
    unknown = set(params) - _ALLOWED_PARAMS
    if unknown:
        _invalid(f"unsupported model parameter(s): {sorted(unknown)}")

    body: dict[str, object] = {"model": model.gateway_model, "messages": messages}
    if "temperature" in params:
        body["temperature"] = _temperature(params["temperature"])
    if "max_tokens" in params:
        body["max_tokens"] = _max_tokens(params["max_tokens"])
    if "reasoning" in params:
        body["reasoning_effort"] = _reasoning(params["reasoning"])
    if tools:
        body["tools"] = list(tools)
    return body


def _temperature(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        _invalid(f"temperature must be a finite number, got {value!r}")
    if not math.isfinite(parsed):
        _invalid(f"temperature must be a finite number, got {value!r}")
    return parsed


def _max_tokens(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        _invalid(f"max_tokens must be a positive integer, got {value!r}")
    if parsed < 1:
        _invalid(f"max_tokens must be a positive integer, got {value!r}")
    return parsed


def _reasoning(value: str) -> str:
    if value not in _REASONING_VALUES:
        _invalid(f"reasoning must be one of {sorted(_REASONING_VALUES)}, got {value!r}")
    return value


def _response_turn(response: httpx.Response, model: ModelRoute) -> AssistantTurn:
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise ResolutionError(f"AI Gateway returned invalid JSON for {model.id!r}") from exc
    if not isinstance(payload, Mapping):
        raise ResolutionError(f"AI Gateway returned an invalid response for {model.id!r}")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise ResolutionError(f"AI Gateway response has no first choice for {model.id!r}")
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        raise ResolutionError(f"AI Gateway response has no text content for {model.id!r}")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise ResolutionError(f"AI Gateway response has invalid text content for {model.id!r}")
    raw_calls = message.get("tool_calls", [])
    if raw_calls is None:
        raw_calls = []
    if not isinstance(raw_calls, list):
        raise ResolutionError(f"AI Gateway response has invalid tool calls for {model.id!r}")
    tool_calls = tuple(_tool_call(value, model) for value in raw_calls)
    if content is None and not tool_calls:
        raise ResolutionError(
            f"AI Gateway response has no text content; assistant has neither text nor tool calls "
            f"for {model.id!r}"
        )
    return AssistantTurn(content, tool_calls)


def _tool_call(value: object, model: ModelRoute) -> ToolCall:
    if not isinstance(value, Mapping) or value.get("type") != "function":
        raise ResolutionError(f"AI Gateway response has an invalid tool call for {model.id!r}")
    call_id = value.get("id")
    function = value.get("function")
    if not isinstance(call_id, str) or not call_id or not isinstance(function, Mapping):
        raise ResolutionError(f"AI Gateway response has an invalid tool call for {model.id!r}")
    name = function.get("name")
    arguments = function.get("arguments")
    if not isinstance(name, str) or not name or not isinstance(arguments, str):
        raise ResolutionError(f"AI Gateway response has an invalid tool call for {model.id!r}")
    return ToolCall(call_id, name, arguments)


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["AssistantTurn", "GatewayClient", "GatewayResponseTooLargeError", "ToolCall"]
