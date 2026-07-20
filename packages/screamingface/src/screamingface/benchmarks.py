"""SDK-local canonical benchmark discovery and loading."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from screamingface._benchmarks.draco import benchmark as draco_benchmark
from screamingface._benchmarks.draco_preview import benchmark as draco_preview_benchmark
from screamingface._benchmarks.gpqa import benchmark as gpqa_benchmark
from screamingface.benchmark import Benchmark
from screamingface.errors import UnknownBenchmarkError
from screamingface.models import _filters, _limit, _query


@dataclass(frozen=True, slots=True)
class _Definition:
    id: str
    tools: tuple[str, ...]
    load: Callable[[], Benchmark]


_DEFINITIONS = (
    _Definition("gpqa@1", (), gpqa_benchmark),
    _Definition("draco@1", ("web_search", "web_fetch"), draco_benchmark),
    _Definition("draco-preview@1", ("web_search", "web_fetch"), draco_preview_benchmark),
)


def list(
    *, query: str | None = None, tools: Sequence[str] = (), limit: int | None = None
) -> builtins.list[str]:
    """Return installed canonical benchmark IDs, optionally filtered in package order."""

    requested_tools = _filters(tools)
    needle = _query(query)
    if limit is not None:
        _limit(limit, 0)
    values = [
        definition.id
        for definition in _DEFINITIONS
        if (needle is None or needle in definition.id.casefold())
        and requested_tools.issubset(definition.tools)
    ]
    return values[: _limit(limit, len(values))]


def load(benchmark_id: str) -> Benchmark:
    """Load one installed definition and fetch its source through the caller's access."""

    if not isinstance(benchmark_id, str) or not benchmark_id.strip():
        raise ValueError("benchmark ID must be a non-empty string")
    requested = benchmark_id.strip()
    definition = next((item for item in _DEFINITIONS if item.id == requested), None)
    if definition is None:
        raise UnknownBenchmarkError(f"unknown benchmark {requested!r}")
    return definition.load()
