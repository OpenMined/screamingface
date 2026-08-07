"""Engine-bound DRACO Case and Check records carried through ordinary URL4 output."""

from __future__ import annotations

import json
from collections.abc import Mapping

CASE_SCHEMA = "screamingface.draco-case-record.v1"
CHECK_SCHEMA = "screamingface.draco-check-record.v1"
_CRITERION_TYPES = frozenset({"positive", "negative"})


def bind_case(
    raw_cases: str, *, case_id: int, output: str, finish_reason: str | None
) -> dict[str, object]:
    """Bind one Candidate output to the Engine-owned Case selected by ``case_id``."""

    selected_id = _case_id(case_id)
    if not isinstance(output, str) or not output.strip():
        raise ValueError("DRACO Candidate output must be non-empty text")
    try:
        cases = json.loads(raw_cases)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"DRACO cases are not JSON: {exc}") from None
    if not isinstance(cases, list):
        raise ValueError("DRACO cases must be a JSON array")
    for row in cases:
        if not isinstance(row, Mapping) or _optional_case_id(row.get("id")) != selected_id:
            continue
        input_value = row.get("input")
        if not isinstance(input_value, str) or not input_value.strip():
            raise ValueError(f"DRACO Case {selected_id} input must be non-empty text")
        return {
            "schema": CASE_SCHEMA,
            "case_id": selected_id,
            "input": input_value,
            "output": output,
            "finish_reason": finish_reason,
            "metadata": {key: value for key, value in row.items() if key not in {"id", "input"}},
        }
    raise ValueError(f"unknown DRACO Case {selected_id}")


def bind_check(
    requirement: str,
    *,
    case_id: int,
    criterion_id: str,
    criterion_type: str,
) -> dict[str, object]:
    """Bind one public criterion description to Engine-known Case identity."""

    selected_type = _text(criterion_type, "criterion_type")
    if selected_type not in _CRITERION_TYPES:
        raise ValueError(f"unsupported DRACO criterion_type {selected_type!r}")
    return {
        "schema": CHECK_SCHEMA,
        "case_id": _case_id(case_id),
        "criterion_id": _text(criterion_id, "criterion_id"),
        "criterion_type": selected_type,
        "requirement": _text(requirement, "criterion requirement"),
    }


def _case_id(value: object) -> int:
    selected = _optional_case_id(value)
    if selected is None or selected < 1:
        raise ValueError("case_id must be a positive integer")
    return selected


def _optional_case_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


__all__ = ["CASE_SCHEMA", "CHECK_SCHEMA", "bind_case", "bind_check"]
