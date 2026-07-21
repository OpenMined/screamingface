from __future__ import annotations

import pytest

import screamingface as sf
from screamingface._benchmarks import draco_lite
from screamingface.benchmark import Case


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
                    "criteria": [{"id": "fact", "requirement": "State the fact", "weight": 4}],
                }
            ],
        },
        metadata={"domain": "Academic"},
    )


def test_lite_keeps_two_complete_real_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    source = (_case(1), _case(2), _case(3))
    monkeypatch.setattr(draco_lite, "draco_cases", lambda: source)

    benchmark = draco_lite.benchmark()

    assert benchmark.id == "draco-lite@1"
    assert benchmark.title == "DRACO Lite"
    assert benchmark._materialize_cases() == source[:2]
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
    assert benchmark.grader.passes == 2
    assert benchmark.grader.params == {
        "temperature": 0.2,
        "reasoning": "low",
        "max_tokens": 4096,
    }


def test_lite_requires_two_source_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(draco_lite, "draco_cases", lambda: (_case(1),))

    with pytest.raises(RuntimeError, match="fewer than two cases"):
        draco_lite.draco_lite_cases()
