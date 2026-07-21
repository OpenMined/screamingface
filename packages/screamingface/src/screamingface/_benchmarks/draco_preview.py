"""Small real-data DRACO profile for development and notebook validation."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache

from screamingface._benchmarks._draco_prompt import DRACO_JUDGE_PROMPT
from screamingface._benchmarks.draco import draco_cases
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import InvalidBenchmarkError
from screamingface.graders import Rubric
from screamingface.tools import WebFetch, WebSearch


def benchmark() -> Benchmark:
    """Build the explicitly non-comparable DRACO development profile."""

    return Benchmark(
        "draco-preview@1",
        title="DRACO Preview",
        cases=draco_preview_cases(),
        grader=Rubric(
            model="openrouter/google/gemini-3.1-pro-preview",
            prompt=DRACO_JUDGE_PROMPT,
            passes=1,
            params={"temperature": 0.2, "reasoning": "low", "max_tokens": 4096},
        ),
        aggregator=Mean(),
        tools=(WebSearch(), WebFetch()),
        max_tool_calls=12,
    )


@cache
def draco_preview_cases() -> tuple[Case, ...]:
    """Keep every real case but only its first positive rubric criterion."""

    return tuple(
        Case(
            case.id,
            case.input,
            reference=_preview_reference(case.reference),
            metadata=case.metadata,
        )
        for case in draco_cases()
    )


def _preview_reference(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidBenchmarkError("DRACO Preview requires an object rubric reference")
    sections = value.get("sections")
    if not isinstance(sections, list):
        raise InvalidBenchmarkError("DRACO Preview requires rubric sections")
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        criterion = _first_positive(section.get("criteria"))
        if criterion is not None:
            return _one_criterion_rubric(value, section, criterion)
    raise InvalidBenchmarkError("DRACO Preview requires a positive rubric criterion")


def _first_positive(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, list):
        return None
    for criterion in value:
        if not isinstance(criterion, Mapping):
            continue
        weight = criterion.get("weight")
        if not isinstance(weight, bool) and isinstance(weight, (int, float)) and weight > 0:
            return criterion
    return None


def _one_criterion_rubric(
    rubric: Mapping[object, object],
    section: Mapping[object, object],
    criterion: Mapping[str, object],
) -> dict[str, object]:
    rubric_fields = _string_fields(rubric)
    section_fields = _string_fields(section)
    return {
        **rubric_fields,
        "sections": [
            {
                **section_fields,
                "criteria": [dict(criterion)],
            }
        ],
    }


def _string_fields(value: Mapping[object, object]) -> dict[str, object]:
    if not all(isinstance(key, str) for key in value):
        raise InvalidBenchmarkError("DRACO Preview rubric fields must have string names")
    return {str(key): item for key, item in value.items()}


__all__ = ["benchmark", "draco_preview_cases"]
