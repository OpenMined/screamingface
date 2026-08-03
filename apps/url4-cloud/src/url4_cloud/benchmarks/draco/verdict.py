"""DRACO's deterministic binding of a Judge reply to an Engine-known criterion."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from url4 import Node, RelExpr, Text, render

SCHEMA = "screamingface.criterion-verdict.v1"


def call(judge: Node, criterion_id: str, *, case_id: str, route: str) -> RelExpr:
    """Wrap a Judge call with the case and criterion identities already known by the Engine."""

    if not isinstance(criterion_id, str) or not criterion_id:
        raise ValueError("criterion_id must be non-empty URL4 text")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case_id must be non-empty URL4 text")
    if not isinstance(route, str) or not route.startswith("/"):
        raise ValueError("criterion verdict route must be an absolute URL4 path")
    return RelExpr(
        path=route,
        context=render(judge, check=False),
        # The case id is numeric, so the first colon is an unambiguous boundary even when an
        # opaque criterion id itself contains colons. The model never sees or supplies either id.
        intent=Text(f"{case_id}:{criterion_id}"),
    )


def binding_key(value: str) -> tuple[int, str]:
    """Decode the internal ``case_id:criterion_id`` intent carried by :func:`call`."""

    case_text, separator, criterion_id = value.partition(":")
    if not separator:
        raise ValueError("criterion verdict binding must contain case_id:criterion_id")
    try:
        case_id = int(case_text)
    except ValueError:
        raise ValueError("criterion verdict case_id must be a positive integer") from None
    if case_id < 1:
        raise ValueError("criterion verdict case_id must be a positive integer")
    return case_id, _text(criterion_id, "criterion_id")


def bind(raw: str, *, case_id: int, criterion_id: str) -> dict[str, object]:
    """Validate ``raw`` and attach Engine-known case and criterion identifiers."""

    if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
        raise ValueError("case_id must be a positive integer")
    selected_id = _text(criterion_id, "criterion_id")
    decoded = _decode_object(raw)
    reason = _invalid_reason(raw, decoded)
    if reason is not None:
        return _invalid(case_id, selected_id, reason)
    assert isinstance(decoded, Mapping)
    explanation = decoded.get("explanation")
    status = decoded.get("criterion_status")
    assert isinstance(explanation, str) and status in ("MET", "UNMET")
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "criterion_id": selected_id,
        "valid": True,
        "explanation": explanation,
        "criterion_status": status,
    }


def _invalid_reason(raw: object, decoded: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        reason = "empty"
    elif decoded is None:
        reason = "invalid_json"
    elif not isinstance(decoded, Mapping):
        reason = "invalid_shape"
    elif not isinstance(decoded.get("explanation"), str) or "criterion_status" not in decoded:
        reason = "invalid_shape"
    elif decoded.get("criterion_status") not in ("MET", "UNMET"):
        reason = "invalid_status"
    else:
        reason = None
    return reason


def _decode_object(raw: object) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = _without_fences(raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _first_json_value(text)


def _without_fences(text: str) -> str:
    if "```" not in text:
        return text
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("```")
    ).strip()


def _first_json_value(text: str) -> Any:
    start = text.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return value


def _invalid(case_id: int, criterion_id: str, reason: str) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "criterion_id": criterion_id,
        "valid": False,
        "reason": reason,
    }


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


__all__ = ["SCHEMA", "bind", "binding_key", "call"]
