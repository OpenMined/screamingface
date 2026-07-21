"""Strict decoding of provider-neutral URL4 tool policies."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from url4 import ResolutionError

WEB_SEARCH = "web_search"
WEB_FETCH = "web_fetch"

_SUPPORTED_TOOLS = frozenset({WEB_SEARCH, WEB_FETCH})
_SEARCH_PREFIX = "web_search."
_FETCH_PREFIX = "web_fetch."
_SEARCH_FIELDS = frozenset({"max_results"})
TOOL_POLICY_SCHEMA = "screamingface.tool-policy.v1"


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    max_results: int
    include_domains: tuple[str, ...]
    exclude_domains: tuple[str, ...]

    def tavily_request_body(self, query: str) -> dict[str, object]:
        """Translate portable policy into the engine's Tavily adapter request."""

        body: dict[str, object] = {
            "query": query,
            "search_depth": "basic",
            "max_results": self.max_results,
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_image_descriptions": False,
            "include_favicon": False,
            "auto_parameters": False,
            "exact_match": False,
            "include_usage": False,
            "safe_search": False,
        }
        if self.include_domains:
            body["include_domains"] = list(self.include_domains)
        if self.exclude_domains:
            body["exclude_domains"] = list(self.exclude_domains)
        return body

    def openrouter_parameters(self, *, max_calls: int) -> dict[str, object]:
        """Translate portable policy into OpenRouter's managed-search surface."""

        values: dict[str, object] = {
            "engine": "auto",
            "max_results": self.max_results,
            # OpenRouter owns its internal agent loop. Bounding total results is
            # the closest server-side equivalent to the portable call budget.
            "max_total_results": self.max_results * max_calls,
        }
        if self.include_domains:
            values["allowed_domains"] = list(self.include_domains)
        if self.exclude_domains:
            values["excluded_domains"] = list(self.exclude_domains)
        return values


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    def tavily_request_body(self, url: str, *, query: str | None) -> dict[str, object]:
        body: dict[str, object] = {
            "urls": [url],
            "extract_depth": "basic",
            "include_images": False,
            "include_favicon": False,
            "format": "markdown",
            "include_usage": False,
        }
        if query is not None:
            body["query"] = query
        return body


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    tools: frozenset[str]
    max_calls: int
    search: SearchPolicy | None
    fetch: FetchPolicy | None


@dataclass(frozen=True, slots=True)
class ParsedToolPolicy:
    model_params: Mapping[str, str]
    policy: ToolPolicy | None


def parse_tool_policy(params: Mapping[str, str]) -> ParsedToolPolicy:
    """Decode untrusted URL4 parameters without importing SDK values."""

    raw_tools = params.get("tools")
    policy_keys = tuple(
        key
        for key in params
        if key == "tools.max_calls"
        or key.startswith(_SEARCH_PREFIX)
        or key.startswith(_FETCH_PREFIX)
    )
    model_params = {
        key: value for key, value in params.items() if key != "tools" and key not in policy_keys
    }
    if raw_tools is None:
        if policy_keys:
            _malformed("tool-free requests cannot contain tool policy")
        return ParsedToolPolicy(model_params, None)

    tools = _tools(raw_tools)
    max_calls = _positive_integer(params.get("tools.max_calls"), "tools.max_calls")

    search_values, include_domains, exclude_domains = _group_search(params)
    fetch_values = tuple(key for key in params if key.startswith(_FETCH_PREFIX))
    if WEB_SEARCH not in tools and (search_values or include_domains or exclude_domains):
        _malformed("web-search policy is present for an undeclared tool")
    if WEB_FETCH not in tools and fetch_values:
        _malformed("web-fetch policy is present for an undeclared tool")
    if fetch_values:
        _malformed(f"unknown web-fetch parameter {fetch_values[0]!r}")

    search = None
    if WEB_SEARCH in tools:
        unknown = set(search_values) - _SEARCH_FIELDS
        if unknown:
            _malformed(f"unknown web-search parameter {sorted(unknown)[0]!r}")
        if "max_results" not in search_values:
            _malformed("web-search policy is missing field: max_results")
        search = SearchPolicy(
            _integer(search_values["max_results"], 1, 20, "web_search.max_results"),
            include_domains,
            exclude_domains,
        )

    return ParsedToolPolicy(
        model_params,
        ToolPolicy(
            frozenset(tools),
            max_calls,
            search,
            FetchPolicy() if WEB_FETCH in tools else None,
        ),
    )


def parse_tool_policy_document(body: str) -> ToolPolicy:
    """Decode one immutable benchmark-policy data-route response."""

    payload = _json_object(body)
    _exact_fields(payload, {"schema", "tools", "max_calls", "web_search"}, "tool policy")
    if payload["schema"] != TOOL_POLICY_SCHEMA:
        _malformed(f"tool policy schema must be {TOOL_POLICY_SCHEMA!r}")
    tools = _document_tools(payload["tools"])
    max_calls = _document_integer(payload["max_calls"], 1, 32, "max_calls")
    raw_search = payload["web_search"]
    search = None
    if WEB_SEARCH in tools:
        if not isinstance(raw_search, dict):
            _malformed("web_search must be an object when web_search is enabled")
        _exact_fields(
            raw_search,
            {"max_results", "include_domains", "exclude_domains"},
            "web_search",
        )
        search = SearchPolicy(
            _document_integer(raw_search["max_results"], 1, 20, "web_search.max_results"),
            _document_domains(raw_search["include_domains"], 150, "include_domains"),
            _document_domains(raw_search["exclude_domains"], 150, "exclude_domains"),
        )
    elif raw_search is not None:
        _malformed("web_search must be null when web_search is disabled")
    return ToolPolicy(
        frozenset(tools),
        max_calls,
        search,
        FetchPolicy() if WEB_FETCH in tools else None,
    )


def _tools(value: str) -> tuple[str, ...]:
    tools = tuple(value.split(":"))
    if not tools or any(not tool for tool in tools) or len(tools) != len(set(tools)):
        _malformed("tools must contain unique non-empty capability IDs")
    unsupported = set(tools) - _SUPPORTED_TOOLS
    if unsupported:
        _unsupported(f"unsupported tool capability: {sorted(unsupported)}")
    return tools


def _document_tools(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        _malformed("tools must be a non-empty list of capability IDs")
    tools = tuple(value)
    if len(tools) != len(set(tools)):
        _malformed("tools must contain unique capability IDs")
    unsupported = set(tools) - _SUPPORTED_TOOLS
    if unsupported:
        _unsupported(f"unsupported tool capability: {sorted(unsupported)}")
    return tools


def _document_domains(value: object, maximum: int, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _malformed(f"{label} must be a list of domain strings")
    values = tuple(_nonblank(item, f"{label} item") for item in value)
    if len(values) > maximum:
        _malformed(f"{label} supports at most {maximum} domains")
    if len(values) != len(set(values)):
        _malformed(f"{label} must be unique")
    return values


def _document_integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _malformed(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _json_object(body: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _malformed(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(body, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise ResolutionError(
            "tool policy route returned invalid JSON",
            code="malformed_tool_policy",
            permanent=True,
        ) from exc
    if not isinstance(value, dict):
        _malformed("tool policy route must return a JSON object")
    return value


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    fields = set(value)
    if fields != expected:
        missing = sorted(expected - fields)
        unknown = sorted(fields - expected)
        _malformed(
            f"{label} fields do not match the contract: missing={missing}, unknown={unknown}"
        )


def _group_search(
    params: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    values: dict[str, str] = {}
    include: dict[int, str] = {}
    exclude: dict[int, str] = {}
    for key, value in params.items():
        if not key.startswith(_SEARCH_PREFIX):
            continue
        field = key.removeprefix(_SEARCH_PREFIX)
        if field.startswith("include_domain."):
            _indexed(include, field.removeprefix("include_domain."), value, "include domains")
        elif field.startswith("exclude_domain."):
            _indexed(exclude, field.removeprefix("exclude_domain."), value, "exclude domains")
        else:
            values[field] = value
    return values, _contiguous(include, "include domains"), _contiguous(exclude, "exclude domains")


def _indexed(target: dict[int, str], raw: str, value: str, label: str) -> None:
    index = _positive_integer(raw, f"{label} index")
    if index in target:
        _malformed(f"duplicate {label} index {index}")
    target[index] = _nonblank(value, f"{label} value")


def _contiguous(values: Mapping[int, str], label: str) -> tuple[str, ...]:
    if not values:
        return ()
    if set(values) != set(range(1, len(values) + 1)):
        _malformed(f"{label} must use contiguous indices starting at 1")
    return tuple(values[index] for index in range(1, len(values) + 1))


def _positive_integer(value: str | None, label: str) -> int:
    if value is None:
        _malformed(f"{label} is required for tool-enabled requests")
    return _integer(value, 1, 32, label, range_message="a positive integer from 1 to 32")


def _integer(
    value: str, minimum: int, maximum: int, label: str, *, range_message: str | None = None
) -> int:
    try:
        parsed = int(value)
    except ValueError:
        _malformed(f"{label} must be {range_message or f'an integer from {minimum} to {maximum}'}")
    if str(parsed) != value or not minimum <= parsed <= maximum:
        _malformed(f"{label} must be {range_message or f'an integer from {minimum} to {maximum}'}")
    return parsed


def _nonblank(value: str, label: str) -> str:
    if not value.strip():
        _malformed(f"{label} must be a non-empty string")
    return value.strip()


def _malformed(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_tool_policy", permanent=True)


def _unsupported(message: str) -> NoReturn:
    raise ResolutionError(message, code="unsupported_tool", permanent=True)


__all__ = [
    "FetchPolicy",
    "ParsedToolPolicy",
    "SearchPolicy",
    "TOOL_POLICY_SCHEMA",
    "ToolPolicy",
    "WEB_FETCH",
    "WEB_SEARCH",
    "parse_tool_policy",
    "parse_tool_policy_document",
]
