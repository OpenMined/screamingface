"""Model discovery from the configured screamingface-engine profile."""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from typing import TYPE_CHECKING

from screamingface._profile import ModelRecord, load_registry
from screamingface._tooling import tool_ids

if TYPE_CHECKING:
    from screamingface._catalog_view import ModelsView


def list(
    *, query: str | None = None, tools: Sequence[str] = (), limit: int | None = None
) -> builtins.list[str]:
    """Return advertised model IDs, optionally filtered in registry order."""

    if limit is not None:
        _limit(limit, 0)
    values = [record.id for record in _filtered_models(query=query, tools=tools)]
    return values[: _limit(limit, len(values))]


def view(*, query: str | None = None, tools: Sequence[str] = ()) -> ModelsView:
    """Return a searchable notebook catalog of advertised models."""

    from screamingface._catalog_view import ModelsView

    return ModelsView(_filtered_models(query=query, tools=tools))


def _filtered_models(*, query: str | None, tools: Sequence[str]) -> builtins.list[ModelRecord]:
    # INVARIANT: view() and list() share this predicate, so they never disagree on membership.
    requested_tools = _filters(tools)
    needle = _query(query)
    return [
        record
        for record in load_registry().models
        if (needle is None or needle in record.id.casefold())
        and requested_tools.issubset(record.supported_tools)
    ]


def _query(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("query must be a non-empty string")
    return value.strip().casefold()


def _filters(values: Sequence[str]) -> set[str]:
    return set(tool_ids(values))


def _limit(value: int | None, total: int) -> int:
    if value is None:
        return total
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("limit must be a positive integer")
    return value
