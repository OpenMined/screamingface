from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError
from typing import Any, TypedDict, Unpack, cast

import pytest
from url4 import Url4Node, build, evaluate_sync

import screamingface as sf
from screamingface._compiler import compile_fusion


def _case() -> sf.Case:
    return sf.Case("q1", "Research this", reference="A")


class _BenchmarkChanges(TypedDict, total=False):
    tools: Sequence[sf.tools.Tool]
    max_tool_rounds: int | None


def _benchmark(**changes: Unpack[_BenchmarkChanges]) -> sf.Benchmark:
    tools = changes.get(
        "tools",
        (sf.tools.TavilySearch(), sf.tools.TavilyExtract()),
    )
    return sf.Benchmark(
        "research@1",
        cases=[_case()],
        grader=sf.graders.ExactChoice(),
        tools=tools,
        max_tool_rounds=changes.get("max_tool_rounds", 12),
    )


def test_tavily_search_is_public_immutable_and_has_stable_defaults() -> None:
    search = sf.tools.TavilySearch()

    assert search.id == "web_search"
    assert search.search_depth == "basic"
    assert search.chunks_per_source is None
    assert search.max_results == 5
    assert search.topic == "general"
    assert search.time_range is None
    assert search.start_date is None
    assert search.end_date is None
    assert search.include_answer is False
    assert search.include_raw_content is False
    assert search.include_images is False
    assert search.include_image_descriptions is False
    assert search.include_favicon is False
    assert search.include_domains == ()
    assert search.exclude_domains == ()
    assert search.country is None
    assert search.auto_parameters is False
    assert search.exact_match is False
    assert search.include_usage is False
    assert search.safe_search is False

    with pytest.raises(FrozenInstanceError):
        setattr(search, "max_results", 10)


def test_tavily_extract_is_public_immutable_and_has_stable_defaults() -> None:
    extract = sf.tools.TavilyExtract()

    assert extract.id == "web_fetch"
    assert extract.extract_depth == "basic"
    assert extract.chunks_per_source is None
    assert extract.include_images is False
    assert extract.include_favicon is False
    assert extract.format == "markdown"
    assert extract.timeout is None
    assert extract.include_usage is False

    with pytest.raises(FrozenInstanceError):
        setattr(extract, "format", "text")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.tools.TavilySearch(search_depth="deep"), "search_depth"),
        (lambda: sf.tools.TavilySearch(chunks_per_source=0), "chunks_per_source"),
        (lambda: sf.tools.TavilySearch(chunks_per_source=4), "chunks_per_source"),
        (
            lambda: sf.tools.TavilySearch(search_depth="basic", chunks_per_source=2),
            "advanced",
        ),
        (lambda: sf.tools.TavilySearch(max_results=-1), "max_results"),
        (lambda: sf.tools.TavilySearch(max_results=21), "max_results"),
        (lambda: sf.tools.TavilySearch(topic="science"), "topic"),
        (lambda: sf.tools.TavilySearch(time_range="quarter"), "time_range"),
        (lambda: sf.tools.TavilySearch(start_date="20-07-2026"), "start_date"),
        (lambda: sf.tools.TavilySearch(end_date="2026-02-30"), "end_date"),
        (
            lambda: sf.tools.TavilySearch(start_date="2026-07-21", end_date="2026-07-20"),
            "start_date",
        ),
        (lambda: sf.tools.TavilySearch(include_answer="yes"), "include_answer"),
        (
            lambda: sf.tools.TavilySearch(include_raw_content="html"),
            "include_raw_content",
        ),
        (
            lambda: sf.tools.TavilySearch(include_image_descriptions=True),
            "include_images",
        ),
        (
            lambda: sf.tools.TavilySearch(include_domains=("example.com", "example.com")),
            "unique",
        ),
        (lambda: sf.tools.TavilySearch(include_domains=("",)), "non-empty"),
        (
            lambda: sf.tools.TavilySearch(include_domains=tuple(f"d{i}.test" for i in range(301))),
            "at most 300",
        ),
        (
            lambda: sf.tools.TavilySearch(exclude_domains=tuple(f"d{i}.test" for i in range(151))),
            "at most 150",
        ),
        (lambda: sf.tools.TavilySearch(topic="news", country="uk"), "general"),
        (
            lambda: sf.tools.TavilySearch(search_depth="fast", safe_search=True),
            "safe_search",
        ),
        (lambda: sf.tools.TavilyExtract(extract_depth="fast"), "extract_depth"),
        (lambda: sf.tools.TavilyExtract(chunks_per_source=0), "chunks_per_source"),
        (lambda: sf.tools.TavilyExtract(chunks_per_source=6), "chunks_per_source"),
        (lambda: sf.tools.TavilyExtract(format="html"), "format"),
        (lambda: sf.tools.TavilyExtract(timeout=0.9), "timeout"),
        (lambda: sf.tools.TavilyExtract(timeout=60.1), "timeout"),
    ],
)
def test_tavily_tool_values_reject_invalid_policy(factory: object, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        cast(Callable[[], object], factory)()


def test_tavily_values_defensively_own_domain_sequences() -> None:
    domains = ["one.example", "two.example"]
    search = sf.tools.TavilySearch(include_domains=domains)
    domains.append("changed.example")

    assert search.include_domains == ("one.example", "two.example")


def test_tavily_extract_accepts_fractional_timeout() -> None:
    assert sf.tools.TavilyExtract(timeout=1.5).timeout == 1.5


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tools": (sf.tools.TavilySearch(),), "max_tool_rounds": None}, "required"),
        ({"tools": (), "max_tool_rounds": 1}, "tool-free"),
        ({"max_tool_rounds": 0}, "positive"),
        ({"max_tool_rounds": True}, "positive"),
        (
            {
                "tools": (sf.tools.TavilySearch(), sf.tools.TavilySearch()),
                "max_tool_rounds": 1,
            },
            "unique",
        ),
        (
            {
                "tools": cast(Sequence[sf.tools.Tool], ("web_search",)),
                "max_tool_rounds": 1,
            },
            "sf.tools",
        ),
    ],
)
def test_benchmark_requires_typed_unique_tools_and_an_explicit_round_budget(
    changes: _BenchmarkChanges, message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _benchmark(**changes)


def test_benchmark_retains_typed_tool_policy_and_round_budget() -> None:
    benchmark = _benchmark()

    assert benchmark.tools == (sf.tools.TavilySearch(), sf.tools.TavilyExtract())
    assert benchmark.max_tool_rounds == 12


def _full_policy_expression() -> tuple[sf.Fusion, str]:
    fusion = sf.Fusion(
        "research",
        inputs=["hf/deepseek-v3", "hf/glm-4"],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Synthesize the panel answers.",
        ),
    )
    search = sf.tools.TavilySearch(
        search_depth="advanced",
        chunks_per_source=3,
        max_results=8,
        topic="news",
        time_range="week",
        start_date="2026-07-01",
        end_date="2026-07-20",
        include_answer="advanced",
        include_raw_content="markdown",
        include_images=True,
        include_image_descriptions=True,
        include_favicon=True,
        include_domains=("one.example", "two.example/path"),
        exclude_domains=("blocked.example",),
        auto_parameters=True,
        exact_match=True,
        include_usage=True,
        safe_search=True,
    )
    extract = sf.tools.TavilyExtract(
        extract_depth="advanced",
        chunks_per_source=5,
        include_images=True,
        include_favicon=True,
        format="text",
        timeout=60,
        include_usage=True,
    )

    return fusion, compile_fusion(
        fusion, question="Research this", tools=(search, extract), max_tool_rounds=12
    )


def test_tavily_policy_compiles_to_scalar_member_params_only() -> None:
    _fusion, expression = _full_policy_expression()

    assert build(expression)
    assert expression.count("tools=web_search+web_fetch") == 2
    assert expression.count("max_tool_rounds=12") == 2
    assert expression.count("tavily.search.search_depth=advanced") == 2
    assert expression.count("tavily.search.include_domain.1=one.example") == 2
    assert expression.count("tavily.search.include_domain.2=two.example/path") == 2
    assert expression.count("tavily.search.exclude_domain.1=blocked.example") == 2
    assert expression.count("tavily.extract.timeout=60") == 2
    assert "fusion_answer=/codex/gpt-5.5?tools=" not in expression
    assert "fusion_answer=/codex/gpt-5.5?max_tool_rounds=" not in expression


def test_tavily_policy_round_trips_through_url4_without_reaching_reducer() -> None:
    _fusion, expression = _full_policy_expression()
    requests: list[Any] = []
    reducer_requests: list[Any] = []
    node = Url4Node("typed-tool-round-trip")

    def member(request):
        requests.append(request)
        return "answer"

    node.endpoint("/hf/deepseek-v3")(member)
    node.endpoint("/hf/glm-4")(member)

    def reducer(request):
        reducer_requests.append(request)
        return "answer"

    node.endpoint("/codex/gpt-5.5")(reducer)
    result = evaluate_sync(expression, node)

    assert result.text
    assert len(requests) == 2
    assert all(request.params["tools"] == "web_search web_fetch" for request in requests)
    assert all(request.params["max_tool_rounds"] == "12" for request in requests)
    assert all(request.params["tavily.extract.format"] == "text" for request in requests)
    assert len(reducer_requests) == 1
    assert reducer_requests[0].params == {}


def test_default_tavily_policy_is_serialized_explicitly_for_reproducibility() -> None:
    fusion = sf.Fusion(
        "research",
        inputs=["hf/deepseek-v3", "hf/glm-4"],
        reducer=sf.reducers.MajorityVote(),
    )

    expression = compile_fusion(
        fusion,
        question="Research this",
        tools=(sf.tools.TavilySearch(), sf.tools.TavilyExtract()),
        max_tool_rounds=8,
    )

    assert expression.count("tavily.search.max_results=5") == 2
    assert expression.count("tavily.search.include_raw_content=false") == 2
    assert expression.count("tavily.search.safe_search=false") == 2
    assert expression.count("tavily.extract.extract_depth=basic") == 2
    assert expression.count("tavily.extract.format=markdown") == 2
    assert "tavily.search.chunks_per_source=" not in expression
    assert "tavily.extract.timeout=" not in expression
    assert "tavily" not in fusion.url4
