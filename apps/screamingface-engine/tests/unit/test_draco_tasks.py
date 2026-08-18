"""DRACO's local case-to-criterion task preparation boundary."""

from __future__ import annotations

import pytest

from screamingface_engine.benchmarks.draco import tasks


def test_build_tasks_combines_answer_with_weight_free_criteria() -> None:
    criteria = [
        {
            "id": "correct",
            "requirement": "The answer is four.",
            "criterion_type": "positive",
        },
        {
            "id": "wrong",
            "requirement": "Claims the answer is five.",
            "criterion_type": "negative",
        },
    ]

    result = tasks.build_tasks(7, "What is two plus two?", "Four.", criteria)

    assert result == [
        {
            "case_id": "7",
            "question": "What is two plus two?",
            "answer": "Four.",
            "criterion_id": "correct",
            "criterion": "The answer is four.",
            "criterion_type": "positive",
        },
        {
            "case_id": "7",
            "question": "What is two plus two?",
            "answer": "Four.",
            "criterion_id": "wrong",
            "criterion": "Claims the answer is five.",
            "criterion_type": "negative",
        },
    ]
    assert all("weight" not in task for task in result)


def test_build_tasks_rejects_invalid_criterion_type() -> None:
    with pytest.raises(tasks.TasksError, match="criterion_type"):
        tasks.build_tasks(
            1,
            "Q",
            "A",
            [{"id": "c", "requirement": "R", "criterion_type": "unknown"}],
        )


def test_build_tasks_sends_an_empty_model_output_to_the_normal_judge() -> None:
    result = tasks.build_tasks(
        1,
        "Question",
        "",
        [{"id": "c", "requirement": "Required", "criterion_type": "positive"}],
    )

    assert result[0]["answer"] == ""
