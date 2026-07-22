"""Provider-neutral benchmark tool policies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

type Tool = WebSearch | WebFetch
type ToolParameter = int | str


@dataclass(frozen=True, slots=True)
class WebSearch:
    """Portable web-search policy resolved by the configured engine.

    The engine may satisfy this capability with provider-managed search or with
    its own search adapter. These fields therefore describe desired behavior,
    not a vendor API.
    """

    id: ClassVar[str] = "web_search"

    max_results: int = 5
    include_domains: Sequence[str] = ()
    exclude_domains: Sequence[str] = ()

    def __post_init__(self) -> None:
        _integer(self.max_results, 1, 20, "max_results")
        object.__setattr__(
            self,
            "include_domains",
            _domains(self.include_domains, 150, "include_domains"),
        )
        object.__setattr__(
            self,
            "exclude_domains",
            _domains(self.exclude_domains, 150, "exclude_domains"),
        )

    def _parameter_items(self) -> tuple[tuple[str, ToolParameter], ...]:
        values: list[tuple[str, ToolParameter]] = [
            ("web_search.max_results", self.max_results),
        ]
        for position, domain in enumerate(self.include_domains, 1):
            values.append((f"web_search.include_domain.{position}", domain))
        for position, domain in enumerate(self.exclude_domains, 1):
            values.append((f"web_search.exclude_domain.{position}", domain))
        return tuple(values)


@dataclass(frozen=True, slots=True)
class WebFetch:
    """Allow the engine-selected web backend to fetch page content."""

    id: ClassVar[str] = "web_fetch"

    def _parameter_items(self) -> tuple[tuple[str, ToolParameter], ...]:
        return ()


def _tool_values(values: Sequence[Tool]) -> tuple[Tool, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("benchmark tools must be a sequence of sf.tools values")
    result = tuple(values)
    if not all(isinstance(value, (WebSearch, WebFetch)) for value in result):
        raise TypeError("benchmark tools must contain only sf.tools values")
    ids = tuple(value.id for value in result)
    if len(ids) != len(set(ids)):
        raise ValueError("benchmark tools must be unique")
    return result


def _tool_ids(values: Sequence[Tool]) -> tuple[str, ...]:
    return tuple(value.id for value in _tool_values(values))


def _integer(value: object, minimum: int, maximum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")


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


__all__ = ["Tool", "WebFetch", "WebSearch"]
