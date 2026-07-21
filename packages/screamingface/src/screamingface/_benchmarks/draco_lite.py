"""Two-case DRACO profile with complete rubrics and two judge passes."""

from __future__ import annotations

from functools import cache

from screamingface._benchmarks._draco_prompt import DRACO_JUDGE_PROMPT
from screamingface._benchmarks.draco import EXCLUDED_RESEARCH_DOMAINS, draco_cases
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark, Case
from screamingface.graders import Rubric
from screamingface.tools import WebFetch, WebSearch


def benchmark() -> Benchmark:
    """Build the small but protocol-faithful DRACO profile."""

    return Benchmark(
        "draco-lite@1",
        title="DRACO Lite",
        cases=draco_lite_cases(),
        grader=Rubric(
            model="openrouter/google/gemini-3.1-pro-preview",
            prompt=DRACO_JUDGE_PROMPT,
            passes=2,
            params={"temperature": 0.2, "reasoning": "low", "max_tokens": 4096},
        ),
        aggregator=Mean(),
        tools=(
            WebSearch(max_results=5, exclude_domains=EXCLUDED_RESEARCH_DOMAINS),
            WebFetch(),
        ),
        max_tool_calls=12,
    )


@cache
def draco_lite_cases() -> tuple[Case, ...]:
    """Return the first two cases from the immutable, pinned DRACO ordering."""

    cases = draco_cases()
    if len(cases) < 2:
        raise RuntimeError("the pinned DRACO dataset contains fewer than two cases")
    return cases[:2]


__all__ = ["benchmark", "draco_lite_cases"]
