"""Bounded engine-owned model/tool execution for named URL4 capabilities."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, NoReturn, Protocol

from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.gateway import AssistantTurn, ToolCall
from screamingface_engine.web_research import SearchResult

_TOOLS_PARAM = "tools"
_WEB_SEARCH = "web_search"

_WEB_TOOL_SPECS: tuple[dict[str, object], ...] = (
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the public web for current evidence. Returns titles, URLs, and snippets."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Read the public text of a URL returned by web_search.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
)


class GatewayPort(Protocol):
    async def turn(
        self,
        model: ModelRoute,
        *,
        messages: list[dict[str, object]],
        params: Mapping[str, str],
        tools: tuple[dict[str, object], ...],
    ) -> AssistantTurn: ...


class ResearchPort(Protocol):
    async def search(self, query: str) -> tuple[SearchResult, ...]: ...

    async def fetch(self, url: str) -> str: ...


class ModelExecutor:
    """Interpret named capabilities while keeping the Gateway transport generic."""

    def __init__(
        self,
        gateway: GatewayPort,
        research: ResearchPort | None,
        *,
        max_tool_calls: int,
    ) -> None:
        self._gateway = gateway
        self._research = research
        self._max_tool_calls = max_tool_calls

    def handler(self, model: ModelRoute):
        async def execute(request: Request) -> str:
            return await self.complete(model, request)

        return execute

    async def complete(self, model: ModelRoute, request: Request) -> str:
        requested = _requested_tools(request.params)
        params = {key: value for key, value in request.params.items() if key != _TOOLS_PARAM}
        if not requested:
            turn = await self._gateway.turn(
                model,
                messages=_initial_messages(request),
                params=params,
                tools=(),
            )
            return _final_text(turn, model)

        unsupported = set(requested) - {_WEB_SEARCH}
        if unsupported:
            _invalid(f"unsupported tool capability: {sorted(unsupported)}")
        if not set(requested).issubset(model.tool_capabilities):
            _invalid(f"model route {model.id!r} does not support {requested!r}")
        if self._research is None:
            _invalid("web_search is not configured on this engine")

        messages = _initial_messages(request)
        call_count = 0
        while True:
            turn = await self._gateway.turn(
                model,
                messages=messages,
                params=params,
                tools=_WEB_TOOL_SPECS,
            )
            if not turn.tool_calls:
                return _final_text(turn, model)
            if call_count + len(turn.tool_calls) > self._max_tool_calls:
                raise ResolutionError(f"model route {model.id!r} exceeded the web tool-call limit")
            messages.append(turn.to_message())
            for tool_call in turn.tool_calls:
                messages.append(await self._tool_message(tool_call))
                call_count += 1

    async def _tool_message(self, tool_call: ToolCall) -> dict[str, object]:
        arguments = _arguments(tool_call)
        assert self._research is not None
        if tool_call.name == "web_search":
            query = _nonblank(arguments.get("query"), "web_search requires a non-empty query")
            _exact_keys(arguments, {"query"}, "web_search arguments")
            results = await self._research.search(query)
            content: dict[str, object] = {"results": [result.to_dict() for result in results]}
        elif tool_call.name == "web_fetch":
            url = _nonblank(arguments.get("url"), "web_fetch requires a non-empty URL")
            _exact_keys(arguments, {"url"}, "web_fetch arguments")
            try:
                fetched = await self._research.fetch(url)
            except ResolutionError as exc:
                if exc.permanent:
                    raise
                content = {"url": url, "error": str(exc)}
            else:
                content = {"url": url, "content": fetched}
        else:
            _invalid(f"model requested undeclared tool {tool_call.name!r}")
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps(content, separators=(",", ":")),
        }


def _requested_tools(params: Mapping[str, str]) -> tuple[str, ...]:
    raw = params.get(_TOOLS_PARAM)
    if raw is None:
        return ()
    tools = tuple(raw.split())
    if not tools or len(set(tools)) != len(tools):
        _invalid("tools must contain unique non-empty capability IDs")
    return tools


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
        raise ResolutionError(f"model route {model.id!r} returned no final text")
    return turn.content


def _arguments(tool_call: ToolCall) -> Mapping[str, Any]:
    try:
        value: Any = json.loads(tool_call.arguments)
    except json.JSONDecodeError:
        _invalid(f"tool {tool_call.name!r} arguments must be a valid JSON object")
    if not isinstance(value, Mapping):
        _invalid(f"tool {tool_call.name!r} arguments must be a valid JSON object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        _invalid(f"{label} must contain exactly {sorted(expected)}")


def _nonblank(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(message)
    return value.strip()


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["ModelExecutor"]
