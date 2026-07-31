"""Decode the Engine's explicit Benchmark catalogue contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class _BenchmarkCatalogData:
    ids: tuple[str, ...]
    default: str | None


def _decode_benchmark_catalog(payload: object) -> _BenchmarkCatalogData:
    root = _mapping(payload, "Benchmark catalog")
    if root.get("object") != "list":
        raise ValueError("Benchmark catalog object must be 'list'")
    if "default" not in root:
        raise ValueError("Benchmark catalog must declare default")
    rows = root.get("data")
    if not isinstance(rows, list):
        raise ValueError("Benchmark catalog must contain a data array")
    ids = _benchmark_ids(rows)
    return _BenchmarkCatalogData(ids=ids, default=_default(root["default"], ids))


def _benchmark_ids(rows: list[object]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        item = _mapping(row, "Benchmark catalog entry")
        if item.get("object") != "benchmark":
            raise ValueError("Benchmark catalog entry object must be 'benchmark'")
        benchmark_id = _text(item.get("id"), "Benchmark id")
        if benchmark_id in seen:
            raise ValueError(f"Benchmark catalog contains duplicate id {benchmark_id!r}")
        seen.add(benchmark_id)
        values.append(benchmark_id)
    return tuple(values)


def _default(value: object, ids: tuple[str, ...]) -> str | None:
    if not ids:
        if value is not None:
            raise ValueError("Empty Benchmark catalog default must be null")
        return None
    selected = _text(value, "Benchmark catalog default")
    if selected not in ids:
        raise ValueError(f"Benchmark catalog default {selected!r} is not installed")
    return selected


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-blank text")
    return value.strip()


__all__: list[str] = []
