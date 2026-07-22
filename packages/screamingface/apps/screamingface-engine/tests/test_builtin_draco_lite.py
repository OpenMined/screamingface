from __future__ import annotations

from typing import Any, cast

import pytest
import screamingface as sf
from screamingface.benchmark import Case

from screamingface_engine.benchmark_definitions import draco_lite


@pytest.fixture(autouse=True)
def clear_lite_cache():
    draco_lite.draco_lite_cases.cache_clear()
    yield
    draco_lite.draco_lite_cases.cache_clear()


def _case(index: int) -> Case:
    return Case(
        f"case-{index}",
        f"Research question {index}",
        reference={
            "id": f"rubric-{index}",
            "sections": [
                {
                    "id": "accuracy",
                    "title": "Accuracy",
                    "criteria": [
                        {"id": "fact", "requirement": "State the fact", "weight": 4},
                        {"id": "error", "requirement": "Avoid the error", "weight": -2},
                        {"id": "detail", "requirement": "Add detail", "weight": 1},
                    ],
                },
                {
                    "id": "reasoning",
                    "title": "Reasoning",
                    "criteria": [
                        {"id": "method", "requirement": "Explain the method", "weight": 2},
                        {"id": "assumption", "requirement": "State assumptions", "weight": 1},
                        {"id": "limitation", "requirement": "Discuss limitations", "weight": 1},
                    ],
                },
                {
                    "id": "evidence",
                    "title": "Evidence",
                    "criteria": [
                        {"id": "source", "requirement": "Cite a source", "weight": 1},
                        {
                            "id": "citation-quality",
                            "requirement": "Use a strong source",
                            "weight": 1,
                        },
                    ],
                },
                {
                    "id": "clarity",
                    "title": "Clarity",
                    "criteria": [
                        {"id": "structure", "requirement": "Structure the answer", "weight": 1},
                        {"id": "precision", "requirement": "Use precise language", "weight": 1},
                    ],
                },
            ],
        },
        metadata={"domain": "Academic"},
    )


def test_lite_keeps_one_real_case_and_ten_diverse_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (_case(1), _case(2), _case(3))
    monkeypatch.setattr(draco_lite, "draco_cases", lambda: source)

    benchmark = draco_lite.benchmark()

    assert benchmark.id == "draco-lite@1"
    assert benchmark.title == "DRACO Lite"
    cases = benchmark._materialize_cases()
    assert len(cases) == 1
    assert cases[0].id == source[0].id
    reference = cast(dict[str, Any], cases[0].reference)
    sections = reference["sections"]
    assert isinstance(sections, list)
    assert [section["id"] for section in sections] == [
        "accuracy",
        "reasoning",
        "evidence",
        "clarity",
    ]
    criteria = [criterion for section in sections for criterion in section["criteria"]]
    assert [criterion["id"] for criterion in criteria] == [
        "fact",
        "error",
        "detail",
        "method",
        "assumption",
        "limitation",
        "source",
        "citation-quality",
        "structure",
        "precision",
    ]
    assert benchmark.tools == (
        sf.tools.WebSearch(
            max_results=5,
            exclude_domains=draco_lite.EXCLUDED_RESEARCH_DOMAINS,
        ),
        sf.tools.WebFetch(),
    )
    assert benchmark.max_tool_calls == 12
    assert isinstance(benchmark.grader, sf.graders.Rubric)
    assert benchmark.grader.model == "openrouter/google/gemini-3.1-pro-preview"
    assert benchmark.grader.passes == 1
    assert benchmark.grader.params == {
        "temperature": 0.2,
        "reasoning": "low",
        "max_tokens": 4096,
    }


def test_lite_requires_one_positive_and_negative_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(1)
    reference = cast(dict[str, Any], case.reference)
    sections = reference["sections"]
    assert isinstance(sections, list)
    sections[0]["criteria"] = [{"id": "fact", "requirement": "State the fact", "weight": 4}]
    invalid = Case(case.id, case.input, reference=reference, metadata=case.metadata)
    monkeypatch.setattr(draco_lite, "draco_cases", lambda: (invalid,))

    with pytest.raises(sf.InvalidBenchmarkError, match="positive and negative"):
        draco_lite.draco_lite_cases()


def test_lite_requires_ten_weighted_criteria(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _case(1)
    reference = cast(dict[str, Any], case.reference)
    sections = cast(list[dict[str, object]], reference["sections"])
    clarity = cast(dict[str, object], sections[-1])
    clarity_criteria = cast(list[dict[str, object]], clarity["criteria"])
    clarity_criteria.pop()
    invalid = Case(case.id, case.input, reference=reference, metadata=case.metadata)
    monkeypatch.setattr(draco_lite, "draco_cases", lambda: (invalid,))

    with pytest.raises(sf.InvalidBenchmarkError, match="at least 10"):
        draco_lite.draco_lite_cases()
