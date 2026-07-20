"""Strict application-side decoding of benchmark-owned Tavily URL4 policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import NoReturn

from url4 import ResolutionError

WEB_SEARCH = "web_search"
WEB_FETCH = "web_fetch"

_SUPPORTED_TOOLS = frozenset({WEB_SEARCH, WEB_FETCH})
_SEARCH_PREFIX = "tavily.search."
_EXTRACT_PREFIX = "tavily.extract."
_SEARCH_REQUIRED = frozenset(
    {
        "search_depth",
        "max_results",
        "topic",
        "include_answer",
        "include_raw_content",
        "include_images",
        "include_image_descriptions",
        "include_favicon",
        "auto_parameters",
        "exact_match",
        "include_usage",
        "safe_search",
    }
)
_SEARCH_OPTIONAL = frozenset(
    {"chunks_per_source", "time_range", "start_date", "end_date", "country"}
)
_EXTRACT_REQUIRED = frozenset(
    {"extract_depth", "include_images", "include_favicon", "format", "include_usage"}
)
_EXTRACT_OPTIONAL = frozenset({"chunks_per_source", "timeout"})
_SEARCH_DEPTHS = frozenset({"advanced", "basic", "fast", "ultra-fast"})
_TOPICS = frozenset({"finance", "general", "news"})
_TIME_RANGES = frozenset({"day", "week", "month", "year", "d", "w", "m", "y"})
_ANSWER_MODES = frozenset({"advanced", "basic"})
_CONTENT_MODES = frozenset({"markdown", "text"})
_EXTRACT_DEPTHS = frozenset({"advanced", "basic"})


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    search_depth: str
    chunks_per_source: int | None
    max_results: int
    topic: str
    time_range: str | None
    start_date: str | None
    end_date: str | None
    include_answer: bool | str
    include_raw_content: bool | str
    include_images: bool
    include_image_descriptions: bool
    include_favicon: bool
    include_domains: tuple[str, ...]
    exclude_domains: tuple[str, ...]
    country: str | None
    auto_parameters: bool
    exact_match: bool
    include_usage: bool
    safe_search: bool

    def request_body(self, query: str) -> dict[str, object]:
        body: dict[str, object] = {
            "query": query,
            "search_depth": self.search_depth,
            "max_results": self.max_results,
            "topic": self.topic,
            "include_answer": self.include_answer,
            "include_raw_content": self.include_raw_content,
            "include_images": self.include_images,
            "include_image_descriptions": self.include_image_descriptions,
            "include_favicon": self.include_favicon,
            "auto_parameters": self.auto_parameters,
            "exact_match": self.exact_match,
            "include_usage": self.include_usage,
            "safe_search": self.safe_search,
        }
        _put(body, "chunks_per_source", self.chunks_per_source)
        _put(body, "time_range", self.time_range)
        _put(body, "start_date", self.start_date)
        _put(body, "end_date", self.end_date)
        if self.include_domains:
            body["include_domains"] = list(self.include_domains)
        if self.exclude_domains:
            body["exclude_domains"] = list(self.exclude_domains)
        _put(body, "country", self.country)
        return body


@dataclass(frozen=True, slots=True)
class ExtractPolicy:
    extract_depth: str
    chunks_per_source: int | None
    include_images: bool
    include_favicon: bool
    format: str
    timeout: float | None
    include_usage: bool

    def request_body(self, url: str, *, query: str | None) -> dict[str, object]:
        body: dict[str, object] = {
            "urls": [url],
            "extract_depth": self.extract_depth,
            "include_images": self.include_images,
            "include_favicon": self.include_favicon,
            "format": self.format,
            "include_usage": self.include_usage,
        }
        _put(body, "query", query)
        _put(body, "chunks_per_source", self.chunks_per_source)
        _put(body, "timeout", self.timeout)
        return body


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    tools: frozenset[str]
    max_rounds: int
    search: SearchPolicy | None
    extract: ExtractPolicy | None


@dataclass(frozen=True, slots=True)
class ParsedToolPolicy:
    model_params: Mapping[str, str]
    policy: ToolPolicy | None


def parse_tool_policy(params: Mapping[str, str]) -> ParsedToolPolicy:
    """Decode untrusted URL4 parameters without importing SDK policy values."""

    raw_tools = params.get("tools")
    tool_keys = tuple(key for key in params if key.startswith("tavily."))
    model_params = {
        key: value
        for key, value in params.items()
        if key not in {"tools", "max_tool_rounds"} and not key.startswith("tavily.")
    }
    if raw_tools is None:
        if "max_tool_rounds" in params or tool_keys:
            _malformed("tool-free requests cannot contain tool policy")
        return ParsedToolPolicy(model_params, None)

    tools = tuple(raw_tools.split())
    if not tools or len(tools) != len(set(tools)):
        _malformed("tools must contain unique non-empty capability IDs")
    unsupported = set(tools) - _SUPPORTED_TOOLS
    if unsupported:
        _unsupported(f"unsupported tool capability: {sorted(unsupported)}")
    max_rounds = _positive_integer(params.get("max_tool_rounds"), "max_tool_rounds")

    search_values, include_domains, exclude_domains = _group_search(params)
    extract_values = _group_extract(params)
    if WEB_SEARCH not in tools and (search_values or include_domains or exclude_domains):
        _malformed("Tavily search policy is present for an undeclared tool")
    if WEB_FETCH not in tools and extract_values:
        _malformed("Tavily extract policy is present for an undeclared tool")
    search = (
        _search(search_values, include_domains, exclude_domains) if WEB_SEARCH in tools else None
    )
    extract = _extract(extract_values) if WEB_FETCH in tools else None
    return ParsedToolPolicy(
        model_params,
        ToolPolicy(frozenset(tools), max_rounds, search, extract),
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
        elif field in _SEARCH_REQUIRED or field in _SEARCH_OPTIONAL:
            values[field] = value
        else:
            _malformed(f"unknown Tavily search parameter {key!r}")
    return values, _contiguous(include, "include domains"), _contiguous(exclude, "exclude domains")


def _group_extract(params: Mapping[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in params.items():
        if not key.startswith(_EXTRACT_PREFIX):
            continue
        field = key.removeprefix(_EXTRACT_PREFIX)
        if field not in _EXTRACT_REQUIRED and field not in _EXTRACT_OPTIONAL:
            _malformed(f"unknown Tavily extract parameter {key!r}")
        values[field] = value
    unknown = [
        key
        for key in params
        if key.startswith("tavily.") and not key.startswith((_SEARCH_PREFIX, _EXTRACT_PREFIX))
    ]
    if unknown:
        _malformed(f"unknown Tavily parameter {unknown[0]!r}")
    return values


def _search(
    values: Mapping[str, str], include_domains: tuple[str, ...], exclude_domains: tuple[str, ...]
) -> SearchPolicy:
    _required(values, _SEARCH_REQUIRED, "search")
    depth = _choice(values["search_depth"], _SEARCH_DEPTHS, "search_depth")
    chunks = _optional_integer(values.get("chunks_per_source"), 1, 3, "chunks_per_source")
    if chunks is not None and depth != "advanced":
        _malformed("chunks_per_source requires search_depth='advanced'")
    start = _optional_date(values.get("start_date"), "start_date")
    end = _optional_date(values.get("end_date"), "end_date")
    if start is not None and end is not None and start > end:
        _malformed("start_date must not be later than end_date")
    topic = _choice(values["topic"], _TOPICS, "topic")
    country = _optional_nonblank(values.get("country"), "country")
    if country is not None and topic != "general":
        _malformed("country is available only when topic='general'")
    images = _boolean(values["include_images"], "include_images")
    descriptions = _boolean(values["include_image_descriptions"], "include_image_descriptions")
    if descriptions and not images:
        _malformed("include_image_descriptions requires include_images=true")
    safe = _boolean(values["safe_search"], "safe_search")
    if safe and depth in {"fast", "ultra-fast"}:
        _malformed("safe_search is incompatible with fast search depths")
    return SearchPolicy(
        depth,
        chunks,
        _integer(values["max_results"], 0, 20, "max_results"),
        topic,
        _optional_choice(values.get("time_range"), _TIME_RANGES, "time_range"),
        start.isoformat() if start is not None else None,
        end.isoformat() if end is not None else None,
        _bool_or_choice(values["include_answer"], _ANSWER_MODES, "include_answer"),
        _bool_or_choice(values["include_raw_content"], _CONTENT_MODES, "include_raw_content"),
        images,
        descriptions,
        _boolean(values["include_favicon"], "include_favicon"),
        include_domains,
        exclude_domains,
        country,
        _boolean(values["auto_parameters"], "auto_parameters"),
        _boolean(values["exact_match"], "exact_match"),
        _boolean(values["include_usage"], "include_usage"),
        safe,
    )


def _extract(values: Mapping[str, str]) -> ExtractPolicy:
    _required(values, _EXTRACT_REQUIRED, "extract")
    return ExtractPolicy(
        _choice(values["extract_depth"], _EXTRACT_DEPTHS, "extract_depth"),
        _optional_integer(values.get("chunks_per_source"), 1, 5, "chunks_per_source"),
        _boolean(values["include_images"], "include_images"),
        _boolean(values["include_favicon"], "include_favicon"),
        _choice(values["format"], _CONTENT_MODES, "format"),
        _optional_number(values.get("timeout"), 1, 60, "timeout"),
        _boolean(values["include_usage"], "include_usage"),
    )


def _required(values: Mapping[str, str], required: frozenset[str], label: str) -> None:
    missing = required - set(values)
    if missing:
        _malformed(f"Tavily {label} policy is missing field(s): {', '.join(sorted(missing))}")


def _indexed(target: dict[int, str], raw: str, value: str, label: str) -> None:
    index = _positive_integer(raw, f"{label} index")
    target[index] = _nonblank(value, f"{label} value")


def _contiguous(values: Mapping[int, str], label: str) -> tuple[str, ...]:
    if not values:
        return ()
    if set(values) != set(range(1, len(values) + 1)):
        _malformed(f"Tavily {label} must use contiguous indices starting at 1")
    return tuple(values[index] for index in range(1, len(values) + 1))


def _positive_integer(value: str | None, label: str) -> int:
    if value is None:
        _malformed(f"{label} is required for tool-enabled requests")
    return _integer(value, 1, 2**31 - 1, label, range_message="a positive integer")


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


def _optional_integer(value: str | None, minimum: int, maximum: int, label: str) -> int | None:
    return None if value is None else _integer(value, minimum, maximum, label)


def _optional_number(value: str | None, minimum: float, maximum: float, label: str) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        _malformed(f"{label} must be a number from {minimum:g} to {maximum:g}")
    if not minimum <= parsed <= maximum:
        _malformed(f"{label} must be a number from {minimum:g} to {maximum:g}")
    return parsed


def _boolean(value: str, label: str) -> bool:
    if value not in {"true", "false"}:
        _malformed(f"{label} must be a boolean")
    return value == "true"


def _choice(value: str, allowed: frozenset[str], label: str) -> str:
    if value not in allowed:
        _malformed(f"{label} must be one of {sorted(allowed)}")
    return value


def _optional_choice(value: str | None, allowed: frozenset[str], label: str) -> str | None:
    return None if value is None else _choice(value, allowed, label)


def _bool_or_choice(value: str, allowed: frozenset[str], label: str) -> bool | str:
    if value in {"true", "false"}:
        return value == "true"
    return _choice(value, allowed, label)


def _optional_date(value: str | None, label: str) -> date | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _malformed(f"{label} must be an ISO YYYY-MM-DD date")
    if parsed.isoformat() != value:
        _malformed(f"{label} must be an ISO YYYY-MM-DD date")
    return parsed


def _optional_nonblank(value: str | None, label: str) -> str | None:
    return None if value is None else _nonblank(value, label)


def _nonblank(value: str, label: str) -> str:
    if not value.strip():
        _malformed(f"{label} must be a non-empty string")
    return value.strip()


def _put(body: dict[str, object], key: str, value: object | None) -> None:
    if value is not None:
        body[key] = value


def _malformed(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_tool_policy", permanent=True)


def _unsupported(message: str) -> NoReturn:
    raise ResolutionError(message, code="unsupported_tool", permanent=True)


__all__ = [
    "ExtractPolicy",
    "ParsedToolPolicy",
    "SearchPolicy",
    "ToolPolicy",
    "WEB_FETCH",
    "WEB_SEARCH",
    "parse_tool_policy",
]
