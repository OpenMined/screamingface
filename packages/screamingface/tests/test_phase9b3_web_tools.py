"""Provider-neutral SDK tool contract tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import screamingface as sf
from screamingface._compiler import _tool_params, compile_recipe


@dataclass(frozen=True)
class _BenchmarkChanges:
    tools: tuple[sf.tools.Tool, ...]
    max_tool_calls: int | None


def _benchmark(**changes: object) -> sf.Benchmark:
    defaults = _BenchmarkChanges(
        (sf.tools.WebSearch(), sf.tools.WebFetch()),
        12,
    )
    return sf.Benchmark(
        "research",
        cases=[sf.Case("q1", "Question", reference="A")],
        grader=sf.graders.ExactChoice(),
        tools=changes.get("tools", defaults.tools),  # type: ignore[arg-type]
        max_tool_calls=changes.get(  # type: ignore[arg-type]
            "max_tool_calls", defaults.max_tool_calls
        ),
    )


def test_web_tools_are_provider_neutral_immutable_values() -> None:
    search = sf.tools.WebSearch(
        max_results=7,
        include_domains=["one.example"],
        exclude_domains=["blocked.example"],
    )
    fetch = sf.tools.WebFetch()

    assert search.id == "web_search"
    assert search.max_results == 7
    assert search.include_domains == ("one.example",)
    assert search.exclude_domains == ("blocked.example",)
    assert fetch.id == "web_fetch"
    assert "Tavily" not in repr(search)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.tools.WebSearch(max_results=0), "1 to 20"),
        (lambda: sf.tools.WebSearch(max_results=21), "1 to 20"),
        (
            lambda: sf.tools.WebSearch(include_domains=("example.com", "example.com")),
            "unique",
        ),
        (lambda: sf.tools.WebSearch(exclude_domains=("",)), "non-empty"),
    ],
)
def test_web_search_rejects_invalid_portable_policy(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tools": (sf.tools.WebSearch(),), "max_tool_calls": None}, "required"),
        ({"tools": (), "max_tool_calls": 1}, "tool-free"),
        ({"max_tool_calls": 0}, "positive"),
        ({"max_tool_calls": 33}, "1 to 32"),
        ({"max_tool_calls": True}, "positive"),
        (
            {
                "tools": (sf.tools.WebSearch(), sf.tools.WebSearch()),
                "max_tool_calls": 1,
            },
            "unique",
        ),
    ],
)
def test_benchmark_validates_tool_policy(changes: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _benchmark(**changes)


def test_compiler_serializes_portable_tool_policy_on_answer_calls_only() -> None:
    first = sf.Model("codex/gpt-5.5", prompt="Answer")
    second = sf.Model("gemini/2.5", prompt="Answer")
    fusion = sf.Fusion(
        "pair",
        members=[first, second],
        reducer=sf.reducers.Model(model="codex/gpt-5.5", prompt="Synthesize"),
    )
    expression = compile_recipe(
        fusion,
        question="Research this",
        tools=(
            sf.tools.WebSearch(
                max_results=5,
                include_domains=("one.example", "two.example"),
                exclude_domains=("blocked.example",),
            ),
            sf.tools.WebFetch(),
        ),
        max_tool_calls=12,
    )

    assert expression.count("tools=web_search:web_fetch") == 2
    assert expression.count("tools.max_calls=12") == 2
    assert expression.count("web_search.max_results=5") == 2
    assert expression.count("web_search.include_domain.1=one.example") == 2
    assert expression.count("web_search.exclude_domain.1=blocked.example") == 2
    assert "recipe_answer:0.0:/codex/gpt-5.5?tools=" not in expression
    assert "tavily." not in expression


def test_tool_parameter_builder_rejects_missing_or_invalid_budget() -> None:
    with pytest.raises(ValueError, match="required"):
        _tool_params((sf.tools.WebSearch(),), None)
    with pytest.raises(ValueError, match="required"):
        _tool_params((sf.tools.WebSearch(),), True)
    with pytest.raises(ValueError, match="positive"):
        _tool_params((sf.tools.WebSearch(),), 0)
