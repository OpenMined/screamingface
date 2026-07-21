"""Engine-advertised canonical benchmark discovery and loading."""

from __future__ import annotations

import builtins
from collections.abc import Sequence

from screamingface._profile import BenchmarkRecord, load_registry
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark
from screamingface.errors import UnknownBenchmarkError
from screamingface.graders import ExactChoice
from screamingface.models import _filters, _limit, _query
from screamingface.tools import TavilyExtract, TavilySearch, Tool


def list(
    *, query: str | None = None, tools: Sequence[str] = (), limit: int | None = None
) -> builtins.list[str]:
    """Return engine-advertised benchmark IDs in stable registry order."""

    requested_tools = _filters(tools)
    needle = _query(query)
    if limit is not None:
        _limit(limit, 0)
    values = [
        benchmark.id
        for benchmark in load_registry().benchmarks
        if (needle is None or needle in benchmark.id.casefold())
        and requested_tools.issubset(benchmark.tools)
    ]
    return values[: _limit(limit, len(values))]


def load(benchmark_id: str) -> Benchmark:
    """Load one immutable benchmark manifest from the configured engine registry."""

    if not isinstance(benchmark_id, str) or not benchmark_id.strip():
        raise ValueError("benchmark ID must be a non-empty string")
    requested = benchmark_id.strip()
    record = next((item for item in load_registry().benchmarks if item.id == requested), None)
    if record is None:
        raise UnknownBenchmarkError(f"unknown benchmark {requested!r}")
    return _benchmark(record)


def _benchmark(record: BenchmarkRecord) -> Benchmark:
    if record.grader.kind != "exact_choice":
        raise ValueError(f"unsupported benchmark grader {record.grader.kind!r}")
    if record.aggregator.kind != "mean":
        raise ValueError(f"unsupported benchmark aggregator {record.aggregator.kind!r}")
    return Benchmark._from_engine(
        record.id,
        title=record.title,
        cases_route=record.cases_route,
        grader=ExactChoice(),
        grader_route=record.grader.route,
        aggregator=Mean(),
        aggregator_route=record.aggregator.route,
        tools=_tools(record.tools),
        max_tool_rounds=record.max_tool_rounds,
    )


def _tools(ids: tuple[str, ...]) -> tuple[Tool, ...]:
    values: builtins.list[Tool] = []
    for tool_id in ids:
        if tool_id == "web_search":
            values.append(TavilySearch())
        elif tool_id == "web_fetch":
            values.append(TavilyExtract())
        else:
            raise ValueError(f"unsupported benchmark tool {tool_id!r}")
    return tuple(values)
