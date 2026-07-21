"""URL4 adapters for deterministic ScreamingFace graders."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import NoReturn

from screamingface._exact_choice import exact_choice_score, validate_exact_reference
from url4 import Request, ResolutionError

from screamingface_engine.evaluation_events import emit_progress

EXACT_CHOICE_ROUTE = "/graders/exact-choice/1"
CASE_GRADE_SCHEMA = "screamingface.case-grade.v1"
RECIPE_RESULT_SCHEMA = "screamingface.recipe-result.v1"


def exact_choice(request: Request) -> str:
    """Grade one resolved Recipe and each member against one sealed choice."""

    if request.params:
        _invalid(f"exact choice does not accept parameters: {sorted(request.params)}")
    recipe = _object(request.context, "exact-choice context")
    case = _object(request.intent, "exact-choice intent")
    _exact_fields(recipe, {"schema", "members", "answer"}, "Recipe result")
    _exact_fields(case, {"benchmark_id", "case_id", "reference"}, "case payload")
    if recipe["schema"] != RECIPE_RESULT_SCHEMA:
        _invalid(f"expected Recipe schema {RECIPE_RESULT_SCHEMA!r}")

    benchmark_id = _nonblank(case["benchmark_id"], "benchmark ID")
    case_id = _nonblank(case["case_id"], "case ID")
    try:
        reference = validate_exact_reference(case["reference"])
    except (TypeError, ValueError) as exc:
        _invalid(str(exc))
    answer = _nonblank(recipe["answer"], "Recipe answer", strip=False)
    members = _members(recipe["members"], reference)
    payload = {
        "schema": CASE_GRADE_SCHEMA,
        "benchmark_id": benchmark_id,
        "case_id": case_id,
        "recipe": _grade(reference, answer),
        "members": members,
    }
    emit_progress("grading", "completed", f"Graded case {case_id}")
    return json.dumps(payload, allow_nan=False, separators=(",", ":"))


def _members(value: object, reference: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or not value:
        _invalid("Recipe members must be a non-empty object")
    members: dict[str, object] = {}
    for position, (member_id, raw) in enumerate(value.items(), 1):
        expected = f"member_{position}"
        if member_id != expected or not isinstance(raw, Mapping):
            _invalid("Recipe members must be contiguous member_1 through member_n objects")
        _exact_fields(raw, {"model", "answer"}, f"member {member_id!r}")
        model = _nonblank(raw["model"], f"member {member_id!r} model")
        answer = _nonblank(raw["answer"], f"member {member_id!r} answer", strip=False)
        members[member_id] = {"model": model, **_grade(reference, answer)}
    return members


def _grade(reference: str, answer: str) -> dict[str, object]:
    return {
        "score": exact_choice_score(reference, answer),
        "metrics": {},
        "coverage": 1.0,
    }


def _object(text: str, label: str) -> dict[str, object]:
    if not text:
        _invalid(f"{label} must be a JSON object")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        _invalid(f"{label} must be a JSON object")
    if not isinstance(value, dict):
        _invalid(f"{label} must be a JSON object")
    return value


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        _invalid(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        _invalid(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def _nonblank(value: object, label: str, *, strip: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} must be a non-blank string")
    return value.strip() if strip else value


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["CASE_GRADE_SCHEMA", "EXACT_CHOICE_ROUTE", "exact_choice"]
