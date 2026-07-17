from __future__ import annotations

from typing import Any

import pytest

import screamingface as sf
from screamingface.benchmarks import _EvaluationCase, _resolve_benchmark
from screamingface.data import load_mock_questions


def test_gpqa_registry_definition_and_mock_case_contract() -> None:
    definition = _resolve_benchmark("  GPQA ")
    loaded = definition.load(sf.Session(mode="mock"), first=1, seed=7)
    case = loaded.cases[0]

    assert definition.id == "gpqa"
    assert definition.name == "GPQA Diamond"
    assert definition.version == "gpqa-diamond-v1"
    assert definition.primary_metric == "accuracy"
    assert definition.grader.name == "exact_choice"
    assert loaded.definition is definition
    assert loaded.display_name == "GPQA-shaped synthetic science fixture"
    assert loaded.dataset_source == "synthetic-gpqa-shaped"
    assert case.id.startswith("synthetic-")
    assert case.prompt.endswith("Reply with only A, B, C, or D.")
    assert case.reference in {"A", "B", "C", "D"}
    assert case.metadata == {"subject": load_mock_questions(1)[0].subject}


@pytest.mark.parametrize("benchmark_id", ["", "   ", None])
def test_benchmark_resolution_requires_a_registered_string(
    benchmark_id: str | None,
) -> None:
    with pytest.raises(ValueError, match="non-empty registered benchmark ID"):
        _resolve_benchmark(benchmark_id)  # type: ignore[arg-type]


def test_benchmark_resolution_reports_available_ids() -> None:
    with pytest.raises(
        ValueError,
        match="unknown benchmark 'missing'; available benchmarks: draco, gpqa",
    ):
        _resolve_benchmark("missing")


@pytest.mark.asyncio
async def test_exact_choice_grader_parses_scores_and_rejects_invalid_answers() -> None:
    grader = _resolve_benchmark("gpqa").grader
    case = _EvaluationCase("case-1", "Choose one", "B")
    engine: Any = object()

    correct = await grader.grade(case, "Answer: b", engine=engine)
    incorrect = await grader.grade(case, "A", engine=engine)
    invalid = await grader.grade(case, "No selection", engine=engine)

    assert (correct.answer, correct.score, correct.metrics, correct.valid) == (
        "B",
        1.0,
        (("accuracy", 1.0),),
        True,
    )
    assert (incorrect.answer, incorrect.score, incorrect.valid) == ("A", 0.0, True)
    assert (invalid.answer, invalid.score, invalid.metrics, invalid.valid) == (
        "",
        0.0,
        (("accuracy", 0.0),),
        False,
    )
    assert invalid.failure_code == "invalid_answer"
    assert invalid.failure_message == "Model did not return A-D"
