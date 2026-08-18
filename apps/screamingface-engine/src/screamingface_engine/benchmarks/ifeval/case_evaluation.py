"""Exact IFEval per-Case framing between URL4 execution and Aggregation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

CASE_EVALUATION_SCHEMA = "screamingface.ifeval-case-evaluation.v1"
CHECK_SCHEMA = "screamingface.ifeval-check.v1"
_FIELDS = frozenset({"schema", "case_id", "attempts"})


def bind_case_evaluation(
    case_id: int,
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind ordered verifier attempts to one Engine-known IFEval Case."""

    selected_id = _positive_case_id(case_id)
    selected = [dict(attempt) for attempt in attempts]
    if not selected:
        raise ValueError("IFEval Case evaluation must contain at least one attempt")
    for sequence, attempt in enumerate(selected, start=1):
        if attempt.get("schema") != CHECK_SCHEMA:
            raise ValueError("IFEval Case evaluation contains an unsupported attempt schema")
        if _optional_case_id(attempt.get("case_id")) != selected_id:
            raise ValueError("IFEval Case evaluation contains an attempt for another Case")
        if _optional_case_id(attempt.get("attempt")) != sequence:
            raise ValueError("IFEval Case evaluation attempts must be consecutive and ordered")
    return {
        "schema": CASE_EVALUATION_SCHEMA,
        "case_id": selected_id,
        "attempts": selected,
    }


def decode_case_evaluation(
    value: Any,
    expected_case_id: int,
) -> tuple[dict[str, Any], ...] | None:
    """Decode one exact envelope without searching nested text or values."""

    decoded = _root_object(value)
    selected: tuple[dict[str, Any], ...] | None = None
    if (
        decoded is not None
        and set(decoded) == _FIELDS
        and decoded.get("schema") == CASE_EVALUATION_SCHEMA
        and _optional_case_id(decoded.get("case_id")) == expected_case_id
    ):
        attempts = decoded.get("attempts")
        if (
            not isinstance(attempts, str | bytes)
            and isinstance(attempts, Sequence)
            and bool(attempts)
            and all(isinstance(attempt, Mapping) for attempt in attempts)
        ):
            candidate = tuple(dict(attempt) for attempt in attempts)
            if all(
                attempt.get("schema") == CHECK_SCHEMA
                and _optional_case_id(attempt.get("case_id")) == expected_case_id
                and _optional_case_id(attempt.get("attempt")) == sequence
                for sequence, attempt in enumerate(candidate, start=1)
            ):
                selected = candidate
    return selected


def _root_object(value: Any) -> dict[str, Any] | None:
    decoded = value
    if isinstance(decoded, str):
        try:
            decoded = json.loads(decoded)
        except ValueError:
            return None
    return dict(decoded) if isinstance(decoded, Mapping) else None


def _positive_case_id(value: object) -> int:
    selected = _optional_case_id(value)
    if selected is None or selected < 1:
        raise ValueError("IFEval Case id must be a positive integer")
    return selected


def _optional_case_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


__all__ = [
    "CASE_EVALUATION_SCHEMA",
    "CHECK_SCHEMA",
    "bind_case_evaluation",
    "decode_case_evaluation",
]
