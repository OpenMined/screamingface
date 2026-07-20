"""Typed benchmark-owned tool policies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

type Tool = TavilySearch | TavilyExtract
type ToolParameter = bool | int | float | str

_SEARCH_DEPTHS = frozenset({"advanced", "basic", "fast", "ultra-fast"})
_TOPICS = frozenset({"finance", "general", "news"})
_TIME_RANGES = frozenset({"day", "week", "month", "year", "d", "w", "m", "y"})
_ANSWER_MODES = frozenset({"advanced", "basic"})
_CONTENT_MODES = frozenset({"markdown", "text"})
_EXTRACT_DEPTHS = frozenset({"advanced", "basic"})


@dataclass(frozen=True, slots=True)
class TavilySearch:
    """Stable Tavily Search request policy for one benchmark."""

    id: ClassVar[str] = "web_search"

    search_depth: str = "basic"
    chunks_per_source: int | None = None
    max_results: int = 5
    topic: str = "general"
    time_range: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    include_answer: bool | str = False
    include_raw_content: bool | str = False
    include_images: bool = False
    include_image_descriptions: bool = False
    include_favicon: bool = False
    include_domains: Sequence[str] = ()
    exclude_domains: Sequence[str] = ()
    country: str | None = None
    auto_parameters: bool = False
    exact_match: bool = False
    include_usage: bool = False
    safe_search: bool = False

    def __post_init__(self) -> None:
        _validate_search_values(self)
        _validate_search_flags(self)
        object.__setattr__(
            self,
            "include_domains",
            _domains(self.include_domains, 300, "include_domains"),
        )
        object.__setattr__(
            self,
            "exclude_domains",
            _domains(self.exclude_domains, 150, "exclude_domains"),
        )
        _validate_search_combinations(self)

    def _parameter_items(self) -> tuple[tuple[str, ToolParameter], ...]:
        values: list[tuple[str, ToolParameter]] = [
            ("tavily.search.search_depth", self.search_depth),
            ("tavily.search.max_results", self.max_results),
            ("tavily.search.topic", self.topic),
            ("tavily.search.include_answer", self.include_answer),
            ("tavily.search.include_raw_content", self.include_raw_content),
            ("tavily.search.include_images", self.include_images),
            (
                "tavily.search.include_image_descriptions",
                self.include_image_descriptions,
            ),
            ("tavily.search.include_favicon", self.include_favicon),
            ("tavily.search.auto_parameters", self.auto_parameters),
            ("tavily.search.exact_match", self.exact_match),
            ("tavily.search.include_usage", self.include_usage),
            ("tavily.search.safe_search", self.safe_search),
        ]
        _optional(values, "tavily.search.chunks_per_source", self.chunks_per_source)
        _optional(values, "tavily.search.time_range", self.time_range)
        _optional(values, "tavily.search.start_date", self.start_date)
        _optional(values, "tavily.search.end_date", self.end_date)
        for position, domain in enumerate(self.include_domains, 1):
            values.append((f"tavily.search.include_domain.{position}", domain))
        for position, domain in enumerate(self.exclude_domains, 1):
            values.append((f"tavily.search.exclude_domain.{position}", domain))
        _optional(values, "tavily.search.country", self.country)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class TavilyExtract:
    """Stable Tavily Extract request policy for one benchmark."""

    id: ClassVar[str] = "web_fetch"

    extract_depth: str = "basic"
    chunks_per_source: int | None = None
    include_images: bool = False
    include_favicon: bool = False
    format: str = "markdown"
    timeout: float | int | None = None
    include_usage: bool = False

    def __post_init__(self) -> None:
        _choice(self.extract_depth, _EXTRACT_DEPTHS, "extract_depth")
        if self.chunks_per_source is not None:
            _integer(self.chunks_per_source, 1, 5, "chunks_per_source")
        _boolean(self.include_images, "include_images")
        _boolean(self.include_favicon, "include_favicon")
        _choice(self.format, _CONTENT_MODES, "format")
        if self.timeout is not None:
            _number(self.timeout, 1, 60, "timeout")
        _boolean(self.include_usage, "include_usage")

    def _parameter_items(self) -> tuple[tuple[str, ToolParameter], ...]:
        values: list[tuple[str, ToolParameter]] = [
            ("tavily.extract.extract_depth", self.extract_depth),
            ("tavily.extract.include_images", self.include_images),
            ("tavily.extract.include_favicon", self.include_favicon),
            ("tavily.extract.format", self.format),
            ("tavily.extract.include_usage", self.include_usage),
        ]
        _optional(values, "tavily.extract.chunks_per_source", self.chunks_per_source)
        _optional(values, "tavily.extract.timeout", self.timeout)
        return tuple(values)


def _tool_values(values: Sequence[Tool]) -> tuple[Tool, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("benchmark tools must be a sequence of sf.tools values")
    result = tuple(values)
    if not all(isinstance(value, (TavilySearch, TavilyExtract)) for value in result):
        raise TypeError("benchmark tools must contain only sf.tools values")
    ids = tuple(value.id for value in result)
    if len(ids) != len(set(ids)):
        raise ValueError("benchmark tools must be unique")
    return result


def _tool_ids(values: Sequence[Tool]) -> tuple[str, ...]:
    return tuple(value.id for value in _tool_values(values))


def _validate_search_values(search: TavilySearch) -> None:
    _choice(search.search_depth, _SEARCH_DEPTHS, "search_depth")
    if search.chunks_per_source is not None:
        _integer(search.chunks_per_source, 1, 3, "chunks_per_source")
        if search.search_depth != "advanced":
            raise ValueError("chunks_per_source requires search_depth='advanced'")
    _integer(search.max_results, 0, 20, "max_results")
    _choice(search.topic, _TOPICS, "topic")
    if search.time_range is not None:
        _choice(search.time_range, _TIME_RANGES, "time_range")
    start = _date(search.start_date, "start_date")
    end = _date(search.end_date, "end_date")
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must not be later than end_date")
    _bool_or_choice(search.include_answer, _ANSWER_MODES, "include_answer")
    _bool_or_choice(search.include_raw_content, _CONTENT_MODES, "include_raw_content")


def _validate_search_flags(search: TavilySearch) -> None:
    for value, label in (
        (search.include_images, "include_images"),
        (search.include_image_descriptions, "include_image_descriptions"),
        (search.include_favicon, "include_favicon"),
        (search.auto_parameters, "auto_parameters"),
        (search.exact_match, "exact_match"),
        (search.include_usage, "include_usage"),
        (search.safe_search, "safe_search"),
    ):
        _boolean(value, label)


def _validate_search_combinations(search: TavilySearch) -> None:
    if search.include_image_descriptions and not search.include_images:
        raise ValueError("include_image_descriptions requires include_images=True")
    if search.country is not None:
        _nonempty(search.country, "country")
        if search.topic != "general":
            raise ValueError("country is available only when topic='general'")
    if search.safe_search and search.search_depth in {"fast", "ultra-fast"}:
        raise ValueError("safe_search is incompatible with fast search depths")


def _choice(value: object, allowed: frozenset[str], label: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{label} must be one of {sorted(allowed)}")


def _integer(value: object, minimum: int, maximum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")


def _boolean(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a boolean")


def _number(value: object, minimum: float, maximum: float, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{label} must be a number from {minimum:g} to {maximum:g}")


def _bool_or_choice(value: object, allowed: frozenset[str], label: str) -> None:
    if isinstance(value, bool):
        return
    _choice(value, allowed, label)


def _date(value: str | None, label: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be an ISO YYYY-MM-DD string or None")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be an ISO YYYY-MM-DD date")
    return parsed


def _domains(values: Sequence[str], maximum: int, label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence")
    result = tuple(_nonempty(value, f"{label} item") for value in values)
    if len(result) > maximum:
        raise ValueError(f"{label} must contain at most {maximum} values")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _optional(
    values: list[tuple[str, ToolParameter]],
    key: str,
    value: ToolParameter | None,
) -> None:
    if value is not None:
        values.append((key, value))


__all__ = ["TavilyExtract", "TavilySearch", "Tool"]
