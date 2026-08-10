"""Turn raw judge replies into trustworthy verdicts, tied to the right rubric item.

The judge model returns free text that *should* be ``{"explanation": ...,
"criteria_met": true/false}`` — but models produce garbage sometimes, and a judge
can never be trusted to say which Case/rubric item it was grading. This module
handles both problems deterministically:

- ``call``  — wires the judge call into the expression so a garbage reply can be
  retried with a fresh sample (see its docstring for the nesting trick).
- ``bind``  — parses one reply into a verdict record, stamping on the
  Engine-known ``case_id``/``rubric_id`` (the judge never sees them), or returns
  a documented ``valid: false`` failure with the raw reply kept for audit.
- ``binding_key`` — decodes the ``case_id:rubric_id`` intent the Engine threads
  through the verdict route.

No model calls happen here — everything is pure parsing and validation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SCHEMA = "screamingface.healthbench-rubric-verdict.v1"


def call(judge: object, *, case_id: str, rubric_id: str, route: str, retry: int):
    """Wrap a judge call so parse retries redraw a FRESH judge sample.

    The problem this solves: the judge sometimes answers with garbage (not the
    JSON we asked for). Garbage is still a *successful* model call — so putting
    ``;retry=`` on the judge itself would never fire; there is no error to retry.

    The trick: nest the judge INSIDE the verdict call (as its context), and put
    ``;retry=`` on the verdict. Now the flow is:

        judge answers → verdict route parses → garbage? → verdict RAISES →
        ``;retry=`` re-resolves the whole nested expression → the judge is
        asked AGAIN → a fresh sample (provider-default temperature) that may
        parse this time.

    This is exactly the reference's own recovery loop — ``grade_sample`` re-asks
    on bad JSON (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py)
    — except bounded at ``retry`` attempts instead of forever.
    Shape follows draco's ``verdict.call``.
    """

    from url4 import Node, RelExpr, Text, render, src

    if not isinstance(judge, Node):
        raise ValueError("verdict call needs a URL4 judge node")
    if not isinstance(route, str) or not route.startswith("/"):
        raise ValueError("rubric verdict route must be an absolute URL4 path")
    if isinstance(retry, bool) or not isinstance(retry, int) or retry < 0:
        raise ValueError("retry must be a non-negative integer")
    return src(
        RelExpr(
            path=route,
            context=render(judge, check=False),
            # The Engine writes both ids into the intent — the judge never sees them.
            intent=Text(f"{case_id}:{rubric_id}"),
        ),
        name="verdict",
        weight=0.0,
        retry=retry,
    )


def binding_key(value: str) -> tuple[int, int]:
    """Decode ``case_id:rubric_id`` — both Engine-assigned positive integers."""

    case_text, separator, rubric_text = value.partition(":")
    if not separator:
        raise ValueError("rubric verdict binding must contain case_id:rubric_id")
    try:
        case_id = int(case_text)
        rubric_id = int(rubric_text)
    except ValueError as exc:
        raise ValueError("rubric verdict case_id and rubric_id must be positive integers") from exc
    if case_id < 1 or rubric_id < 1:
        raise ValueError("rubric verdict case_id and rubric_id must be positive integers")
    return case_id, rubric_id


def bind(
    raw: str,
    *,
    case_id: int,
    rubric_id: int,
    producer_id: str,
) -> dict[str, object]:
    """Turn one raw judge reply into a verdict record, or a documented failure.

    The judge was asked for ``{"explanation": ..., "criteria_met": true/false}``.
    This function decides whether what came back counts as a verdict:

    - Parseable with a REAL JSON boolean ``criteria_met`` → ``valid: true`` plus
      the verdict. A string ``"true"`` or a ``1`` does NOT count — the reference
      ``grade_sample`` loops until ``label is True or label is False``
      (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py),
      so anything else is an invalid reply, never a lenient yes.
    - Anything else (empty, bad JSON, wrong shape, non-bool) → ``valid: false``
      with a ``reason`` and the raw output kept for audit.

    Note it RETURNS the failure instead of raising: the caller (runtime's verdict
    route) decides what a failure means — retry first, then fail the Case loudly
    with this record as the evidence.

    The Engine stamps ``case_id``/``rubric_id`` on here itself; the judge never
    saw those ids and cannot be trusted to echo them.
    """

    if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
        raise ValueError("case_id must be a positive integer")
    if isinstance(rubric_id, bool) or not isinstance(rubric_id, int) or rubric_id < 1:
        raise ValueError("rubric_id must be a positive integer")
    selected_producer = _text(producer_id, "producer_id")
    decoded = _decode_object(raw)
    reason = _invalid_reason(raw, decoded)
    common: dict[str, object] = {
        "schema": SCHEMA,
        "case_id": case_id,
        "rubric_id": rubric_id,
        "producer_type": "model",
        "producer_id": selected_producer,
        "raw_output": raw,
    }
    if reason is not None:
        return {**common, "valid": False, "reason": reason}
    assert isinstance(decoded, Mapping)
    criteria_met = decoded.get("criteria_met")
    assert criteria_met is True or criteria_met is False
    explanation = decoded.get("explanation")
    return {
        **common,
        "valid": True,
        "criteria_met": criteria_met,
        "explanation": explanation if isinstance(explanation, str) else "",
    }


def _invalid_reason(raw: object, decoded: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        reason = "empty"
    elif decoded is None:
        reason = "invalid_json"
    elif not isinstance(decoded, Mapping):
        reason = "invalid_shape"
    # WHY: `is True / is False`, not truthiness — mirrors the reference's strict-bool
    # gate and the July port's StrictBool; "true"/1 must trigger a retry, not a verdict.
    elif not (decoded.get("criteria_met") is True or decoded.get("criteria_met") is False):
        reason = "invalid_criteria_met"
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


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


__all__ = ["SCHEMA", "bind", "binding_key"]
