"""Bounded engine-owned model and Tavily agent execution."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any, NoReturn, Protocol

from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.gateway import AssistantTurn, ToolCall
from screamingface_engine.tool_policy import (
    WEB_FETCH,
    WEB_SEARCH,
    ExtractPolicy,
    SearchPolicy,
    ToolPolicy,
    parse_tool_policy,
)

MAX_TOOL_CALLS_PER_TURN = 8
MAX_TOTAL_TOOL_CALLS = 32

_TOOL_SPECS: Mapping[str, dict[str, object]] = {
    WEB_SEARCH: {
        "type": "function",
        "function": {
            "name": WEB_SEARCH,
            "description": (
                "Search the web for current evidence, titles, URLs, and relevant content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural-language search query.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    WEB_FETCH: {
        "type": "function",
        "function": {
            "name": WEB_FETCH,
            "description": "Extract clean content from a specific web URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to extract."},
                    "query": {
                        "type": "string",
                        "description": "Optional query used to select relevant chunks.",
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
}


class GatewayPort(Protocol):
    async def turn(
        self,
        model: ModelRoute,
        *,
        messages: list[dict[str, object]],
        params: Mapping[str, str],
        tools: tuple[dict[str, object], ...],
    ) -> AssistantTurn: ...


class TavilyPort(Protocol):
    async def is_connected(self) -> bool: ...

    async def search(self, query: str, policy: SearchPolicy) -> dict[str, object]: ...

    async def extract(
        self,
        url: str,
        policy: ExtractPolicy,
        *,
        query: str | None,
    ) -> dict[str, object]: ...


class ModelExecutor:
    """Interpret benchmark tool policy while keeping Gateway transport generic."""

    def __init__(self, gateway: GatewayPort, tavily: TavilyPort) -> None:
        self._gateway = gateway
        self._tavily = tavily

    def handler(self, model: ModelRoute):
        async def execute(request: Request) -> str:
            return await self.complete(model, request)

        return execute

    async def complete(self, model: ModelRoute, request: Request) -> str:
        parsed = parse_tool_policy(request.params)
        policy = parsed.policy
        if policy is None:
            turn = await self._gateway.turn(
                model,
                messages=_initial_messages(request),
                params=parsed.model_params,
                tools=(),
            )
            return _final_text(turn, model)

        unsupported = policy.tools - set(model.tool_capabilities)
        if unsupported:
            _resolution(
                f"model route {model.id!r} does not support {sorted(unsupported)}",
                "unsupported_tool",
                permanent=True,
            )
        if not await self._tavily.is_connected():
            _resolution(
                "Connect Tavily before using benchmark tools.",
                "authentication_required",
                permanent=True,
            )
        return await self._run_agent(model, request, parsed.model_params, policy)

    async def _run_agent(
        self,
        model: ModelRoute,
        request: Request,
        params: Mapping[str, str],
        policy: ToolPolicy,
    ) -> str:
        messages = _initial_messages(request)
        specifications = tuple(
            _TOOL_SPECS[name] for name in (WEB_SEARCH, WEB_FETCH) if name in policy.tools
        )
        total_calls = 0
        tool_counts: Counter[str] = Counter()
        for round_index in range(policy.max_rounds):
            turn = await self._gateway.turn(
                model,
                messages=messages,
                params=params,
                tools=specifications,
            )
            if not turn.tool_calls:
                return _final_text(turn, model)
            if round_index + 1 == policy.max_rounds:
                _round_budget(model, policy.max_rounds, tool_counts)
            if len(turn.tool_calls) > MAX_TOOL_CALLS_PER_TURN:
                _budget(model, "per-turn tool-call")
            if total_calls + len(turn.tool_calls) > MAX_TOTAL_TOOL_CALLS:
                _budget(model, "total tool-call")
            messages.append(turn.to_message())
            for tool_call in turn.tool_calls:
                # INVARIANT: One model turn's calls execute in emitted order for reference parity.
                messages.append(await self._tool_message(tool_call, policy))
                total_calls += 1
                if tool_call.name in {WEB_SEARCH, WEB_FETCH}:
                    tool_counts[tool_call.name] += 1
        raise AssertionError("bounded agent loop exhausted without returning or raising")

    async def _tool_message(self, tool_call: ToolCall, policy: ToolPolicy) -> dict[str, object]:
        try:
            content = await self._tool_result(tool_call, policy)
        except _ToolArgumentsError as exc:
            content = {
                "error": {
                    "code": "invalid_tool_arguments",
                    "message": str(exc),
                }
            }
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps(content, separators=(",", ":"), ensure_ascii=False),
        }

    async def _tool_result(self, tool_call: ToolCall, policy: ToolPolicy) -> dict[str, object]:
        arguments = _arguments(tool_call)
        if tool_call.name == WEB_SEARCH and policy.search is not None:
            _exact_keys(arguments, {"query"}, WEB_SEARCH)
            query = _nonblank(arguments.get("query"), "web_search requires a non-empty query")
            return await self._tavily.search(query, policy.search)
        if tool_call.name == WEB_FETCH and policy.extract is not None:
            _allowed_keys(arguments, {"url", "query"}, WEB_FETCH)
            url = _nonblank(arguments.get("url"), "web_fetch requires a non-empty URL")
            query = _optional_nonblank(arguments.get("query"), "web_fetch query")
            if policy.extract.chunks_per_source is not None and query is None:
                raise _ToolArgumentsError(
                    "web_fetch requires query when chunks_per_source is configured."
                )
            return await self._tavily.extract(url, policy.extract, query=query)
        raise _ToolArgumentsError(f"Tool {tool_call.name!r} was not declared.")


class _ToolArgumentsError(ValueError):
    """A model-emitted tool call can be corrected in a subsequent model turn."""


def _arguments(tool_call: ToolCall) -> Mapping[str, Any]:
    try:
        value: Any = json.loads(tool_call.arguments, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise _ToolArgumentsError("Invalid JSON object.") from exc
    if not isinstance(value, Mapping):
        raise _ToolArgumentsError("Invalid JSON object.")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate field {key!r}")
        value[key] = item
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise _ToolArgumentsError(f"{name} arguments must contain exactly {sorted(expected)}.")


def _allowed_keys(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise _ToolArgumentsError(f"{name} has unknown argument(s): {sorted(unknown)}.")


def _nonblank(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _ToolArgumentsError(f"{message}.")
    return value.strip()


def _optional_nonblank(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _nonblank(value, f"{label} must be non-empty")


def _initial_messages(request: Request) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    if request.intent:
        messages.append({"role": "system", "content": request.intent})
    messages.append({"role": "user", "content": request.context})
    return messages


def _final_text(turn: AssistantTurn, model: ModelRoute) -> str:
    if turn.tool_calls:
        raise ResolutionError(f"model route {model.id!r} returned undeclared tool calls")
    if turn.content is None or not turn.content.strip():
        raise ResolutionError(
            f"model route {model.id!r} returned no final text",
            code="invalid_provider_response",
        )
    return turn.content


def _budget(model: ModelRoute, limit: str) -> NoReturn:
    _resolution(
        f"model route {model.id!r} exceeded the {limit} limit",
        "tool_budget_exhausted",
        permanent=True,
    )


def _round_budget(model: ModelRoute, max_rounds: int, counts: Counter[str]) -> NoReturn:
    count_text = ", ".join(
        f"{name}={counts[name]}" for name in (WEB_SEARCH, WEB_FETCH) if counts[name]
    )
    _resolution(
        f"model route {model.id!r} exhausted max_tool_rounds={max_rounds} after "
        f"{max_rounds} model turns (executed tool calls: {count_text or 'none'})",
        "tool_budget_exhausted",
        permanent=True,
    )


def _resolution(message: str, code: str, *, permanent: bool = False) -> NoReturn:
    raise ResolutionError(message, code=code, permanent=permanent)


__all__ = ["MAX_TOOL_CALLS_PER_TURN", "MAX_TOTAL_TOOL_CALLS", "ModelExecutor"]
