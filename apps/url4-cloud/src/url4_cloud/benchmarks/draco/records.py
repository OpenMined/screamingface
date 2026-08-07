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
    raw_cases: str, *, case_id: int, output: str, finish_reason: str | None
) -> dict[str, object]:
    """Bind one Candidate output to the Engine-owned Case selected by ``case_id``."""

    selected_id = require_positive_integer(case_id, "case_id")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("DRACO Candidate output must be non-empty text")
    try:
        cases = json.loads(raw_cases)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"DRACO cases are not JSON: {exc}") from None
    if not isinstance(cases, list):
        raise ValueError("DRACO cases must be a JSON array")
    for row in cases:
        if not isinstance(row, Mapping) or optional_integer(row.get("id")) != selected_id:
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
