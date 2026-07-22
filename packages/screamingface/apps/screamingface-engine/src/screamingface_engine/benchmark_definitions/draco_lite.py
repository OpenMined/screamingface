"""One-case DRACO miniature with ten diverse criteria and one judge pass."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import cache

from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import InvalidBenchmarkError
from screamingface.graders import Rubric
from screamingface.tools import WebFetch, WebSearch

from screamingface_engine.benchmark_definitions._draco_prompt import DRACO_JUDGE_PROMPT
from screamingface_engine.benchmark_definitions.draco import (
    EXCLUDED_RESEARCH_DOMAINS,
    draco_cases,
)

type _WeightedCriterion = tuple[Mapping[object, object], Mapping[object, object], float]

_CRITERIA_LIMIT = 10


def benchmark() -> Benchmark:
    """Build the small but protocol-faithful DRACO profile."""

    return Benchmark(
        "draco-lite@1",
        title="DRACO Lite",
        cases=draco_lite_cases(),
        grader=Rubric(
            model="openrouter/google/gemini-3.1-pro-preview",
            prompt=DRACO_JUDGE_PROMPT,
            passes=1,
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
    """Return one pinned case with ten deterministic, section-diverse criteria."""

    cases = draco_cases()
    if not cases:
        raise RuntimeError("the pinned DRACO dataset contains no cases")
    case = cases[0]
    return (
        Case(
            case.id,
            case.input,
            reference=_lite_reference(case.reference),
            metadata=case.metadata,
        ),
    )


def _lite_reference(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidBenchmarkError("DRACO Lite requires an object rubric reference")
    sections = value.get("sections")
    if not isinstance(sections, list):
        raise InvalidBenchmarkError("DRACO Lite requires rubric sections")
    criteria = _diverse_criteria(sections, limit=_CRITERIA_LIMIT)
    selected: list[dict[str, object]] = []
    for section, criterion, _weight in criteria:
        _append_criterion(selected, section, criterion)
    return {**_string_fields(value), "sections": selected}


def _diverse_criteria(sections: list[object], *, limit: int) -> tuple[_WeightedCriterion, ...]:
    weighted = tuple(_weighted_criteria(sections))
    positive, negative = _signed_pair(weighted)
    if len(weighted) < limit:
        raise InvalidBenchmarkError(
            f"DRACO Lite requires at least {limit} non-zero-weight criteria"
        )

    selected = [positive, negative]
    _append_new_sections(selected, weighted, limit)
    _append_remaining(selected, weighted, limit)
    return tuple(selected)


def _signed_pair(weighted: tuple[_WeightedCriterion, ...]) -> tuple[_WeightedCriterion, ...]:
    positive = next((item for item in weighted if item[2] > 0), None)
    negative = next((item for item in weighted if item[2] < 0), None)
    if positive is None or negative is None:
        raise InvalidBenchmarkError("DRACO Lite requires positive and negative criteria")
    return positive, negative


def _append_new_sections(
    selected: list[_WeightedCriterion],
    weighted: tuple[_WeightedCriterion, ...],
    limit: int,
) -> None:
    represented = {id(item[0]) for item in selected}
    for item in weighted:
        if len(selected) == limit:
            return
        if id(item[0]) not in represented:
            selected.append(item)
            represented.add(id(item[0]))


def _append_remaining(
    selected: list[_WeightedCriterion],
    weighted: tuple[_WeightedCriterion, ...],
    limit: int,
) -> None:
    chosen = {id(item[1]) for item in selected}
    for item in weighted:
        if len(selected) == limit:
            return
        if id(item[1]) not in chosen:
            selected.append(item)
            chosen.add(id(item[1]))


def _weighted_criteria(
    sections: list[object],
) -> Iterable[_WeightedCriterion]:
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        criteria = section.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, Mapping):
                continue
            weight = criterion.get("weight")
            if isinstance(weight, bool) or not isinstance(weight, int | float) or weight == 0:
                continue
            yield section, criterion, float(weight)


def _append_criterion(
    selected: list[dict[str, object]],
    section: Mapping[object, object],
    criterion: Mapping[object, object],
) -> None:
    section_fields = _string_fields(section)
    section_id = section_fields.get("id")
    existing = next((item for item in selected if item.get("id") == section_id), None)
    if existing is None:
        existing = {**section_fields, "criteria": []}
        selected.append(existing)
    raw_criteria = existing["criteria"]
    assert isinstance(raw_criteria, list)
    raw_criteria.append(_string_fields(criterion))


def _string_fields(value: Mapping[object, object]) -> dict[str, object]:
    if not all(isinstance(key, str) for key in value):
        raise InvalidBenchmarkError("DRACO Lite rubric fields must have string names")
    return {str(key): item for key, item in value.items()}


__all__ = ["benchmark", "draco_lite_cases"]
