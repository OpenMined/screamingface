"""In-process adapter from URL4 model requests to the shared AI Gateway."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

import httpx
from url4 import Request, ResolutionError

from screamingface_engine.catalog import GatewayModel, ModelRoute

_ALLOWED_PARAMS = frozenset({"temperature", "max_tokens", "reasoning"})
_REASONING_VALUES = frozenset({"low", "medium", "high"})
_GATEWAY_CODE_MAP = {
    "auth_required": "connection_needs_reauth",
    "connection_not_found": "connection_needs_reauth",
    "profile_not_found": "connection_needs_reauth",
    "profile_pending_auth": "connection_pending",
    "access_denied": "provider_access_denied",
    "bad_request": "invalid_model_request",
    "rate_limited": "rate_limited",
    "provider_unavailable": "provider_unavailable",
}
_TRANSIENT_GATEWAY_CODES = frozenset(
    {"gateway_timeout", "gateway_unavailable", "provider_unavailable", "rate_limited"}
)


class GatewayResponseTooLargeError(Exception):
    """An internal Gateway response exceeded its caller's explicit byte budget."""


class GatewayCatalogError(RuntimeError):
    """AI Gateway model discovery could not produce a safe startup snapshot."""


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

    async def list_models(self) -> tuple[GatewayModel, ...]:
        """Read and strictly decode AI Gateway's protected startup model catalog."""

        try:
            response = await self.request("GET", "/v1/models")
        except httpx.TimeoutException as exc:
            raise GatewayCatalogError("AI Gateway model catalog timed out") from exc
        except httpx.RequestError as exc:
            raise GatewayCatalogError("AI Gateway model catalog is unavailable") from exc
        if not response.is_success:
            raise GatewayCatalogError(
                f"AI Gateway model catalog returned HTTP {response.status_code}"
            )
        try:
            payload: Any = json.loads(response.text, object_pairs_hook=_unique_object)
            return _model_catalog(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayCatalogError(f"invalid AI Gateway model catalog: {exc}") from exc

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
            raise ResolutionError(
                f"AI Gateway timed out while running {model.id!r}",
                code="gateway_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _gateway_status_error(exc.response, model) from exc
        except httpx.RequestError as exc:
            raise ResolutionError(
                f"AI Gateway is unavailable while running {model.id!r}",
                code="gateway_unavailable",
            ) from exc
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


def _model_catalog(payload: Any) -> tuple[GatewayModel, ...]:
    # INVARIANT: Startup never constructs routes from an ambiguous or partially decoded catalog.
    if not isinstance(payload, dict):
        raise TypeError("catalog must be an object")
    _exact_fields(payload, {"object", "data"}, "catalog")
    if payload["object"] != "list":
        raise ValueError("catalog object must be 'list'")
    data = payload["data"]
    if not isinstance(data, list):
        raise TypeError("catalog data must be a list")
    models: list[GatewayModel] = []
    identities: set[tuple[str, str]] = set()
    for index, value in enumerate(data):
        if not isinstance(value, dict):
            raise TypeError(f"catalog model {index} must be an object")
        _exact_fields(value, {"id", "object", "owned_by"}, f"catalog model {index}")
        if value["object"] != "model":
            raise ValueError(f"catalog model {index} object must be 'model'")
        model = GatewayModel(
            _nonblank(value["id"], f"catalog model {index} ID"),
            _nonblank(value["owned_by"], f"catalog model {index} owner"),
        )
        identity = (model.owned_by, model.id)
        if identity in identities:
            raise ValueError(f"duplicate catalog model {model.id!r} for {model.owned_by!r}")
        identities.add(identity)
        models.append(model)
    return tuple(models)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate field {key!r}")
        value[key] = item
    return value


def _exact_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise ValueError(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


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
    tool_calls = _response_tool_calls(message.get("tool_calls", []), model)
    if content is None and not tool_calls:
        raise ResolutionError(
            f"AI Gateway response has no text content; assistant has neither text nor tool calls "
            f"for {model.id!r}"
        )
    return AssistantTurn(content, tool_calls)


def _response_tool_calls(value: object, model: ModelRoute) -> tuple[ToolCall, ...]:
    raw_calls = [] if value is None else value
    if not isinstance(raw_calls, list):
        raise ResolutionError(f"AI Gateway response has invalid tool calls for {model.id!r}")
    calls: list[ToolCall] = []
    for raw in raw_calls:
        if _is_managed_tool_record(raw, model):
            # Managed OpenRouter tools have already executed server-side. Their
            # records are telemetry, not function calls for this engine to run.
            continue
        calls.append(_tool_call(raw, model))
    return tuple(calls)


def _is_managed_tool_record(value: object, model: ModelRoute) -> bool:
    if model.tool_backend != "openrouter" or not isinstance(value, Mapping):
        return False
    tool_type = value.get("type")
    return isinstance(tool_type, str) and tool_type.startswith("openrouter:")


def _gateway_status_error(response: httpx.Response, model: ModelRoute) -> ResolutionError:
    status = response.status_code
    upstream_code, upstream_message = _gateway_error_detail(response)
    code = _normalized_gateway_code(status, upstream_code)
    # INVARIANT: Raw Gateway/provider messages never cross the public URL4 error boundary.
    reason = _safe_provider_reason(upstream_message)
    if reason == "model unavailable":
        code = "model_unavailable"
    classification = code if reason is None else f"{code}; {reason}"
    message = f"AI Gateway returned HTTP {status} ({classification}) for {model.id!r}"
    return ResolutionError(
        message,
        code=code,
        permanent=code not in _TRANSIENT_GATEWAY_CODES,
    )


def _gateway_error_detail(response: httpx.Response) -> tuple[str | None, str | None]:
    try:
        payload: Any = response.json()
    except ValueError:
        return None, None
    if not isinstance(payload, Mapping):
        return None, None
    detail = payload.get("detail")
    if not isinstance(detail, Mapping):
        return None, None
    code = detail.get("code")
    message = detail.get("message")
    safe_code = code if isinstance(code, str) and code else None
    raw_message = message if isinstance(message, str) and message else None
    return safe_code, raw_message


def _safe_provider_reason(message: str | None) -> str | None:
    if message is None:
        return None
    normalized = message.lower()
    if "setup unreachable" in normalized:
        reason = "provider setup unreachable"
    elif "setup did not return" in normalized:
        reason = "provider setup incomplete"
    elif "request unreachable" in normalized:
        reason = "provider request unreachable"
    elif "response is not json" in normalized or "response not json" in normalized:
        reason = "invalid provider response"
    elif "response missing candidates" in normalized:
        reason = "provider response missing candidates"
    elif "model" in normalized and "no longer available" in normalized:
        reason = "model unavailable"
    else:
        reason = None
    return reason


def _normalized_gateway_code(status: int, upstream_code: str | None) -> str:
    if upstream_code in _GATEWAY_CODE_MAP:
        code = _GATEWAY_CODE_MAP[upstream_code]
    elif (
        status == 401
        or status == 404
        and upstream_code
        in {
            "connection_not_found",
            "profile_not_found",
        }
    ):
        code = "connection_needs_reauth"
    elif status == 402:
        code = "payment_required"
    elif status == 403:
        code = "provider_access_denied"
    elif status == 429:
        code = "rate_limited"
    elif status >= 500:
        code = "provider_unavailable"
    elif status == 400:
        code = "invalid_model_request"
    else:
        code = "model_request_rejected"
    return code


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
