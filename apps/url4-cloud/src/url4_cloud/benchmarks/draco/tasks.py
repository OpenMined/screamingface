"""Prepare weight-free DRACO judge tasks at the case-to-criterion scope boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class TasksError(ValueError):
    """The case payload or prepared criterion data is unusable."""


def build_tasks(
    case_id: int,
    question: str,
    answer: str,
    criteria: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Join one dynamic Candidate answer to Engine-owned, weight-free judge inputs."""
    selected_case_id = positive_case_id(case_id)
    selected_question = _text(question, "question")
    selected_answer = _text(answer, "answer")

    tasks: list[dict[str, str]] = []
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, Mapping):
            raise TasksError(f"criterion {index} must be a JSON object")
        criterion_type = _text(criterion.get("criterion_type"), "criterion_type")
        if criterion_type not in {"positive", "negative"}:
            raise TasksError(f"criterion {index} has invalid criterion_type {criterion_type!r}")
        tasks.append(
            {
                "case_id": str(selected_case_id),
                "question": selected_question,
                "answer": selected_answer,
                "criterion_id": _text(criterion.get("id"), "criterion id"),
                "criterion": _text(criterion.get("requirement"), "criterion requirement"),
                "criterion_type": criterion_type,
            }
        )
    if not tasks:
        raise TasksError(f"case {selected_case_id} has no judge criteria")
    return tasks


def load_criteria(directory: Path, case_id: int) -> list[dict[str, Any]]:
    path = directory / f"{case_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TasksError(f"could not read criteria for case {case_id}: {exc}") from None
    except ValueError as exc:
        raise TasksError(f"criteria for case {case_id} are not JSON: {exc}") from None
    if not isinstance(value, list):
        raise TasksError(f"criteria for case {case_id} must be a JSON array")
    return value


def load_question(directory: Path, case_id: int) -> str:
    path = directory.parent / "cases.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TasksError(f"could not read DRACO cases: {exc}") from None
    except ValueError as exc:
        raise TasksError(f"DRACO cases are not JSON: {exc}") from None
    if not isinstance(value, list):
        raise TasksError("DRACO cases must be a JSON array")
    for row in value:
        if isinstance(row, Mapping) and _case_id(row.get("id")) == case_id:
            return _text(row.get("input"), "question")
    raise TasksError(f"unknown DRACO case {case_id}")


def positive_case_id(value: object) -> int:
    """Decode the case id carried in a Benchmark route intent."""
    label = "case_id"
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TasksError(f"{label} must be a positive integer")
    try:
        selected = int(value)
    except ValueError:
        raise TasksError(f"{label} must be a positive integer") from None
    if selected < 1:
        raise TasksError(f"{label} must be a positive integer")
    return selected


def _case_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TasksError(f"{label} must be non-empty text")
    return value


__all__ = [
    "TasksError",
    "build_tasks",
    "load_criteria",
    "load_question",
    "positive_case_id",
]
