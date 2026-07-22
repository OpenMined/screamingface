"""Model discovery from the configured screamingface-engine profile."""

from __future__ import annotations

import builtins
from collections.abc import Sequence

from screamingface._profile import load_registry
from screamingface._tooling import tool_ids


def list(
    *, query: str | None = None, tools: Sequence[str] = (), limit: int | None = None
) -> builtins.list[str]:
    """Return advertised model IDs, optionally filtered in registry order."""

    requested_tools = _filters(tools)
    needle = _query(query)
    if limit is not None:
        _limit(limit, 0)
    records = load_registry().models
    values = [
        record.id
        for record in records
        if (needle is None or needle in record.id.casefold())
        and requested_tools.issubset(record.supported_tools)
    ]
    return values[: _limit(limit, len(values))]


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
