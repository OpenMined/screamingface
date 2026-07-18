"""Benchmark discovery and loading from the configured engine profile."""

from __future__ import annotations

import builtins
from collections.abc import Sequence

from screamingface._profile import load_benchmark, load_registry
from screamingface.benchmark import Benchmark
from screamingface.models import _filters, _limit, _query


def list(
    *, query: str | None = None, tools: Sequence[str] = (), limit: int | None = None
) -> builtins.list[str]:
    """Return advertised benchmark IDs, optionally filtered in registry order."""

    requested_tools = _filters(tools)
    needle = _query(query)
    if limit is not None:
        _limit(limit, 0)
    records = load_registry().benchmarks
    values = [
        record.id
        for record in records
        if (needle is None or needle in record.id.casefold())
        and requested_tools.issubset(record.tools)
    ]
    return values[: _limit(limit, len(values))]


def load(benchmark_id: str) -> Benchmark:
    """Eagerly load and validate one benchmark manifest and normalized case stream."""

    return load_benchmark(benchmark_id)
