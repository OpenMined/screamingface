"""Shared decoding helpers for the ScreamingFace engine HTTP boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx


def engine_error(response: httpx.Response) -> tuple[str, str] | None:
    """Decode the safe URL4 error envelope, returning None for unknown bodies."""

    try:
        payload = unique_json_object(response.text)
        exact_fields(payload, {"error"}, "engine error")
        error = object_value(payload["error"], "engine error")
        exact_fields(error, {"code", "message"}, "engine error")
        return nonblank(error["code"], "engine error code"), nonblank(
            error["message"], "engine error message"
        )
    except (KeyError, TypeError, ValueError):
        return None


def unique_json_object(body: str) -> dict[str, object]:
    """Decode one object while rejecting duplicate JSON fields."""

    try:
        payload = json.loads(body, object_pairs_hook=unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("response is not JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("expected a JSON object")
    return payload


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON object-pairs hook shared by whole-body and embedded decoders."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def exact_fields(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise ValueError(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def object_value(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


__all__ = [
    "engine_error",
    "exact_fields",
    "nonblank",
    "object_value",
    "unique_json_object",
    "unique_object",
]
