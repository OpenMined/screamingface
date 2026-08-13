"""Engine-bound DRACO Case and Check records carried through ordinary URL4 output."""

from __future__ import annotations

import json
from collections.abc import Mapping

from url4_cloud.benchmarks.draco.validation import (
    optional_integer,
    require_positive_integer,
    require_text,
)

CASE_SCHEMA = "screamingface.draco-case-record.v1"
CHECK_SCHEMA = "screamingface.draco-check-record.v1"
_CRITERION_TYPES = frozenset({"positive", "negative"})


def bind_case(
    raw_cases: str,
    *,
    case_id: int,
    answer: str,
    output: str | None,
    refusal: str | None,
    finish_reason: str | None,
) -> dict[str, object]:
    """Bind evaluator text and exact Candidate outcome to one Engine-owned Case."""

    selected_id = require_positive_integer(case_id, "case_id")
    _validate_outcome(answer, output, refusal)
    cases = _decode_cases(raw_cases)
    row = next(
        (
            value
            for value in cases
            if isinstance(value, Mapping) and optional_integer(value.get("id")) == selected_id
        ),
        None,
    )
    if row is None:
        raise ValueError(f"unknown DRACO Case {selected_id}")
    input_value = row.get("input")
    if not isinstance(input_value, str) or not input_value.strip():
        raise ValueError(f"DRACO Case {selected_id} input must be non-empty text")
    return {
        "schema": CASE_SCHEMA,
        "case_id": selected_id,
        "input": input_value,
        "answer": answer,
        "output": output,
        "finish_reason": finish_reason,
        "refusal": refusal,
        "metadata": {key: value for key, value in row.items() if key not in {"id", "input"}},
    }


def _validate_outcome(answer: object, output: object, refusal: object) -> None:
    if not isinstance(answer, str):
        raise ValueError("DRACO Candidate answer must be text")
    if (refusal is None) == (output is None):
        raise ValueError("DRACO Candidate must carry exactly one of output or refusal")
    if refusal is not None and (
        not isinstance(refusal, str) or not refusal.strip() or answer != refusal
    ):
        raise ValueError("DRACO Candidate refusal must be exact non-empty evaluator text")
    if output is not None and answer != output:
        raise ValueError("DRACO Candidate output must equal evaluator text")


def _decode_cases(raw_cases: str) -> list[object]:
    try:
        cases = json.loads(raw_cases)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"DRACO cases are not JSON: {exc}") from None
    if not isinstance(cases, list):
        raise ValueError("DRACO cases must be a JSON array")
    return cases


def bind_check(
    requirement: str,
    *,
    case_id: int,
    criterion_id: str,
    criterion_type: str,
) -> dict[str, object]:
    """Bind one public criterion description to Engine-known Case identity."""

    selected_type = require_text(criterion_type, "criterion_type")
    if selected_type not in _CRITERION_TYPES:
        raise ValueError(f"unsupported DRACO criterion_type {selected_type!r}")
    return {
        "schema": CHECK_SCHEMA,
        "case_id": require_positive_integer(case_id, "case_id"),
        "criterion_id": require_text(criterion_id, "criterion_id"),
        "criterion_type": selected_type,
        "requirement": require_text(requirement, "criterion requirement"),
    }


__all__ = ["CASE_SCHEMA", "CHECK_SCHEMA", "bind_case", "bind_check"]
