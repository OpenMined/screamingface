"""Internal contracts for named model capabilities carried through URL4."""

from __future__ import annotations

import re
from collections.abc import Sequence

TOOL_PARAMETER = "tools"

_TOOL_ID = re.compile(r"[a-z][a-z0-9_]*\Z")


def tool_id(value: object, label: str = "tool") -> str:
    """Normalize one stable lowercase capability identifier."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    normalized = value.strip()
    if _TOOL_ID.fullmatch(normalized) is None:
        raise ValueError(
            f"{label} must start with a lowercase letter and contain only "
            "lowercase letters, digits, and underscores"
        )
    return normalized


def tool_ids(values: Sequence[str], *, label: str = "tools") -> tuple[str, ...]:
    """Validate one ordered, unique capability sequence."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence")
    result = tuple(tool_id(value, f"{label} item") for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def encoded_tools(values: Sequence[str]) -> str:
    """Encode ordered capabilities for URL4's scalar query-parameter surface."""

    return "+".join(tool_ids(values))


__all__ = ["TOOL_PARAMETER", "encoded_tools", "tool_id", "tool_ids"]
