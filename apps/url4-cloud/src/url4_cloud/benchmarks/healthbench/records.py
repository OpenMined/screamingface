"""Engine-bound HealthBench Case and Rubric records carried through ordinary URL4 output."""

from __future__ import annotations

import json
from collections.abc import Mapping

CASE_SCHEMA = "screamingface.healthbench-case-record.v1"
RUBRIC_SCHEMA = "screamingface.healthbench-rubric-record.v1"


def bind_case(
    raw_cases: str, *, case_id: int, output: str, finish_reason: str | None
) -> dict[str, object]:
    """Bind one Candidate output to the Engine-owned Case selected by ``case_id``."""

    selected_id = _case_id(case_id)
    if not isinstance(output, str) or not output.strip():
        raise ValueError("HealthBench Candidate output must be non-empty text")
    try:
        cases = json.loads(raw_cases)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"HealthBench cases are not JSON: {exc}") from None
    if not isinstance(cases, list):
        raise ValueError("HealthBench cases must be a JSON array")
    for row in cases:
        if not isinstance(row, Mapping) or _optional_case_id(row.get("id")) != selected_id:
            continue
        input_value = row.get("input")
        if not isinstance(input_value, str) or not input_value.strip():
            raise ValueError(f"HealthBench Case {selected_id} input must be non-empty text")
        return {
            "schema": CASE_SCHEMA,
            "case_id": selected_id,
            "input": input_value,
            "output": output,
            "finish_reason": finish_reason,
            "metadata": {key: value for key, value in row.items() if key not in {"id", "input"}},
        }
    raise ValueError(f"unknown HealthBench Case {selected_id}")


def bind_rubric_item(
    rubric_item: str,
    *,
    case_id: int,
    rubric_id: int,
) -> dict[str, object]:
    """Bind one rendered ``[points] criterion`` line to Engine-known identities.

    WHY: the judge sees points in the rendered item (the official template's own
    examples reference negative point values) — there is no weight-blinding here,
    unlike DRACO. The numeric points still live ONLY in the private rubric assets;
    the aggregate reads them there, never from anything a model produced.
    """

    if isinstance(rubric_id, bool) or not isinstance(rubric_id, int) or rubric_id < 1:
        raise ValueError("rubric_id must be a positive integer")
    return {
        "schema": RUBRIC_SCHEMA,
        "case_id": _case_id(case_id),
        "rubric_id": rubric_id,
        "rubric_item": _text(rubric_item, "rubric_item"),
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


__all__ = ["CASE_SCHEMA", "RUBRIC_SCHEMA", "bind_case", "bind_rubric_item"]
