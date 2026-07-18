"""In-process adapter from URL4 model requests to the shared AI Gateway."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, NoReturn

import httpx
from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute

_ALLOWED_PARAMS = frozenset({"temperature", "max_tokens", "reasoning"})
_REASONING_VALUES = frozenset({"low", "medium", "high"})


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

    def handler(self, model: ModelRoute) -> Callable[[Request], Awaitable[str]]:
        async def execute(request: Request) -> str:
            return await self.complete(model, request)

        return execute

    async def complete(self, model: ModelRoute, request: Request) -> str:
        body = _request_body(model, request)
        client = await self._get_client()
        try:
            response = await client.post("/v1/chat/completions", json=body)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ResolutionError(f"AI Gateway timed out while running {model.id!r}") from exc
        except httpx.HTTPStatusError as exc:
            raise ResolutionError(
                f"AI Gateway returned HTTP {exc.response.status_code} for {model.id!r}"
            ) from exc
        except httpx.RequestError as exc:
            raise ResolutionError(f"AI Gateway request failed for {model.id!r}: {exc}") from exc
        return _response_text(response, model)

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout,
                    transport=self._transport,
                )
            return self._client


def _request_body(model: ModelRoute, request: Request) -> dict[str, object]:
    unknown = set(request.params) - _ALLOWED_PARAMS
    if unknown:
        _invalid(f"unsupported model parameter(s): {sorted(unknown)}")

    messages: list[dict[str, str]] = []
    if request.intent:
        messages.append({"role": "system", "content": request.intent})
    messages.append({"role": "user", "content": request.context})

    body: dict[str, object] = {"model": model.gateway_model, "messages": messages}
    if "temperature" in request.params:
        body["temperature"] = _temperature(request.params["temperature"])
    if "max_tokens" in request.params:
        body["max_tokens"] = _max_tokens(request.params["max_tokens"])
    if "reasoning" in request.params:
        body["reasoning_effort"] = _reasoning(request.params["reasoning"])
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


def _response_text(response: httpx.Response, model: ModelRoute) -> str:
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
    if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
        raise ResolutionError(f"AI Gateway response has no text content for {model.id!r}")
    return message["content"]


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["GatewayClient"]
