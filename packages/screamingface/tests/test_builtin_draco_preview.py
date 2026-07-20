from __future__ import annotations

from typing import cast

import pytest

import screamingface as sf
from screamingface._benchmarks import draco_preview
from screamingface.benchmark import Case


@pytest.fixture(autouse=True)
def clear_preview_cache():
    draco_preview.draco_preview_cases.cache_clear()
    yield
    draco_preview.draco_preview_cases.cache_clear()


def _case() -> Case:
    return Case(
        "case-1",
        "Research question",
        reference={
            "id": "rubric-1",
            "sections": [
                {
                    "id": "accuracy",
                    "title": "Accuracy",
                    "criteria": [
                        {"id": "penalty", "requirement": "Avoid an error", "weight": -2},
                        {"id": "fact", "requirement": "State the fact", "weight": 4},
                    ],
                },
                {
                    "id": "style",
                    "title": "Style",
                    "criteria": [
                        {"id": "clear", "requirement": "Be clear", "weight": 1},
                    ],
                },
            ],
        },
        metadata={"domain": "Academic"},
    )


def test_preview_uses_real_cases_with_one_real_positive_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(draco_preview, "draco_cases", lambda: (_case(),))

    benchmark = sf.benchmarks.load("draco-preview@1")
    cases = benchmark._materialize_cases()

    assert benchmark.id == "draco-preview@1"
    assert benchmark.title == "DRACO Preview"
    assert benchmark.tools == ("web_search",)
    assert isinstance(benchmark.grader, sf.graders.Rubric)
    assert benchmark.grader.model == "gemini/3.5-flash"
    assert benchmark.grader.passes == 1
    assert benchmark.grader.params == {"temperature": 0.2, "max_tokens": 4096}
    assert cases[0].id == "case-1"
    assert cases[0].input == "Research question"
    assert cases[0].metadata == {"domain": "Academic"}
    reference = cast(dict[str, object], cases[0].reference)
    sections = cast(list[dict[str, object]], reference["sections"])
    criteria = cast(list[dict[str, object]], sections[0]["criteria"])
    assert sections[0]["id"] == "accuracy"
    assert criteria == [{"id": "fact", "requirement": "State the fact", "weight": 4}]


def test_preview_is_explicitly_discoverable_but_does_not_replace_draco() -> None:
    assert sf.benchmarks.list() == ["gpqa@1", "draco@1", "draco-preview@1"]
    assert sf.benchmarks.list(query="preview") == ["draco-preview@1"]
    assert sf.benchmarks.list(tools=["web_search"]) == ["draco@1", "draco-preview@1"]


def test_preview_requires_a_positive_criterion() -> None:
    reference = cast(dict[str, object], _case().reference)
    sections = cast(list[dict[str, object]], reference["sections"])
    for section in sections:
        criteria = cast(list[dict[str, object]], section["criteria"])
        for criterion in criteria:
            criterion["weight"] = -1

    with pytest.raises(sf.InvalidBenchmarkError, match="positive rubric criterion"):
        draco_preview._preview_reference(reference)
