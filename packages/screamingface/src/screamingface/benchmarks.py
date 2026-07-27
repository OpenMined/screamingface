"""Engine-advertised canonical benchmark discovery and loading."""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from typing import TYPE_CHECKING

from screamingface._profile import BenchmarkRecord, load_registry
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark
from screamingface.errors import UnknownBenchmarkError
from screamingface.graders import ExactChoice, Grader, Rubric
from screamingface.models import _filters, _limit, _query
from screamingface.tools import Tool, WebFetch, WebSearch

if TYPE_CHECKING:
    from screamingface._catalog_view import BenchmarksView


def list(
    *, query: str | None = None, tools: Sequence[str] = (), limit: int | None = None
) -> builtins.list[str]:
    """Return engine-advertised benchmark IDs in stable registry order."""

    if limit is not None:
        _limit(limit, 0)
    values = [record.id for record in _filtered_benchmarks(query=query, tools=tools)]
    return values[: _limit(limit, len(values))]


def view(*, query: str | None = None, tools: Sequence[str] = ()) -> BenchmarksView:
    """Return a searchable notebook catalog of engine-advertised benchmarks."""

    from screamingface._catalog_view import BenchmarksView

    return BenchmarksView(_filtered_benchmarks(query=query, tools=tools))


def _filtered_benchmarks(
    *, query: str | None, tools: Sequence[str]
) -> builtins.list[BenchmarkRecord]:
    # INVARIANT: view() and list() share this predicate, so they never disagree on membership.
    requested_tools = _filters(tools)
    needle = _query(query)
    return [
        record
        for record in load_registry().benchmarks
        if (needle is None or needle in record.id.casefold())
        and requested_tools.issubset(record.tools)
    ]


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
    if record.aggregator.kind != "mean":
        raise ValueError(f"unsupported benchmark aggregator {record.aggregator.kind!r}")
    return Benchmark._from_engine(
        record.id,
        title=record.title,
        cases_route=record.cases_route,
        grader=_grader(record),
        grader_route=record.grader.route,
        aggregator=Mean(),
        aggregator_route=record.aggregator.route,
        candidate_route=record.candidate_route,
        candidate_aggregator_route=record.candidate_aggregator_route,
        tool_policy_route=record.tool_policy_route,
        tools=_tools(record.tools),
        max_tool_calls=record.max_tool_calls,
    )


def _grader(record: BenchmarkRecord) -> Grader:
    strategy = record.grader
    if strategy.kind == "exact_choice":
        return ExactChoice()
    if strategy.kind == "rubric":
        if strategy.model is None or strategy.prompt is None or strategy.passes is None:
            raise ValueError("rubric grader manifest is incomplete")
        return Rubric(
            model=strategy.model,
            prompt=strategy.prompt,
            passes=strategy.passes,
            params=strategy.params,
        )
    raise ValueError(f"unsupported benchmark grader {strategy.kind!r}")


def _tools(ids: tuple[str, ...]) -> tuple[Tool, ...]:
    values: builtins.list[Tool] = []
    for tool_id in ids:
        if tool_id == "web_search":
            values.append(WebSearch())
        elif tool_id == "web_fetch":
            values.append(WebFetch())
        else:
            raise ValueError(f"unsupported benchmark tool {tool_id!r}")
    return tuple(values)
