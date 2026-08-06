"""Harvest schema-marked JSON records from nested URL4 result prose."""

from __future__ import annotations

import json
from typing import Any


def harvest_records(row: Any, schema: str, max_depth: int = 5) -> list[dict[str, Any]]:
    """Read complete records without interpreting URL4's presentation scaffolding."""

    pending = [(_as_text(row), 0)]
    visited: set[str] = set()
    found: dict[str, dict[str, Any]] = {}
    while pending:
        text, depth = pending.pop()
        if text in visited:
            continue
        visited.add(text)
        for embedded in _embedded_json_values(text):
            for value in _nested_values(embedded):
                if isinstance(value, dict) and value.get("schema") == schema:
                    key = json.dumps(
                        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                    )
                    found.setdefault(key, value)
                elif isinstance(value, str) and depth < max_depth and "{" in value:
                    pending.append((value, depth + 1))
    return list(found.values())


def _embedded_json_values(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while index < len(text):
        starts = [position for token in ("{", '"') if (position := text.find(token, index)) >= 0]
        if not starts:
            break
        start = min(starts)
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        values.append(value)
        index = start + max(end, 1)
    return values


def _as_text(row: Any) -> str:
    return row if isinstance(row, str) else json.dumps(row)


def _nested_values(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _nested_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_values(item)


__all__ = ["harvest_records"]
