"""Schema-validated HealthBench evaluation envelopes — lossless per-Case artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from url4_cloud.benchmarks.healthbench.records import CASE_SCHEMA, RUBRIC_SCHEMA
from url4_cloud.benchmarks.healthbench.verdict import SCHEMA as VERDICT_SCHEMA

RUBRIC_EVALUATION_SCHEMA = "screamingface.healthbench-rubric-evaluation.v1"
CASE_EVALUATION_SCHEMA = "screamingface.healthbench-case-evaluation.v1"


def bind_rubric_evaluation(
    case_id: int,
    case_record: Mapping[str, Any] | None,
    rubric_record: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Bundle one rubric item's record and its judge evidence into one envelope.

    Think of it as stapling three papers together for one checklist item: what
    the Candidate said (the Case record), what the checklist item was (the
    rubric record), and what the judge decided (the evidence) — after checking
    all three carry the right schema and actually belong to this Case and item.

    WHY the Case record can be ``None``: a Case with 12 rubric items would
    otherwise store the Candidate's full output 12 times. So the full record
    rides on the FIRST rubric row only; the others carry ``{}`` → ``None`` here
    (same artifact-dedup rule as DRACO). ``bind_case_evaluation`` reassembles it.
    """

    selected = _positive(case_id, "case_id")
    if case_record is not None:
        _require_schema(case_record, CASE_SCHEMA, "Case record")
        _require_case(case_record, selected, "Case record")
    _require_schema(rubric_record, RUBRIC_SCHEMA, "Rubric record")
    _require_case(rubric_record, selected, "Rubric record")
    _require_schema(evidence, VERDICT_SCHEMA, "Rubric verdict")
    _require_case(evidence, selected, "Rubric verdict")
    if evidence.get("rubric_id") != rubric_record.get("rubric_id"):
        raise ValueError("Rubric verdict and record disagree on rubric_id")
    return {
        "schema": RUBRIC_EVALUATION_SCHEMA,
        "case_id": selected,
        "rubric_id": rubric_record.get("rubric_id"),
        "case": dict(case_record) if case_record is not None else None,
        "rubric": dict(rubric_record),
        "evidence": dict(evidence),
    }


def bind_case_evaluation(
    case_id: int,
    rubric_evaluations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bundle one Case's rubric rows into the per-Case artifact, hoisting the Case record.

    The inverse of the dedup in ``bind_rubric_evaluation``: exactly ONE incoming
    row must carry the embedded Case record (the first one); it gets hoisted to
    the top level and stripped from the rows. Zero carriers or two carriers both
    raise — as does a duplicated rubric_id — because either means the fan-out
    upstream misbehaved, and a quietly-wrong artifact would poison scoring.
    """

    selected = _positive(case_id, "case_id")
    if not rubric_evaluations:
        raise ValueError("Case evaluation needs at least one rubric evaluation")
    case_record: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for index, row in enumerate(rubric_evaluations, start=1):
        _require_schema(row, RUBRIC_EVALUATION_SCHEMA, f"Rubric evaluation {index}")
        _require_case(row, selected, f"Rubric evaluation {index}")
        rubric_id = row.get("rubric_id")
        if rubric_id in seen:
            raise ValueError(f"duplicate rubric_id {rubric_id!r} in Case {selected}")
        seen.add(rubric_id)
        embedded = row.get("case")
        if embedded is not None:
            if case_record is not None:
                raise ValueError(f"Case {selected} carries more than one Case record")
            if not isinstance(embedded, Mapping):
                raise ValueError("embedded Case record must be an object")
            case_record = dict(embedded)
        stripped = dict(row)
        stripped.pop("case", None)
        rows.append(stripped)
    if case_record is None:
        raise ValueError(f"Case {selected} carries no Case record")
    return {
        "schema": CASE_EVALUATION_SCHEMA,
        "case_id": selected,
        "case": case_record,
        "rubric_evaluations": rows,
    }


def _require_schema(value: Mapping[str, Any], schema: str, label: str) -> None:
    if not isinstance(value, Mapping) or value.get("schema") != schema:
        raise ValueError(f"{label} must carry schema {schema}")


def _require_case(value: Mapping[str, Any], case_id: int, label: str) -> None:
    if value.get("case_id") != case_id:
        raise ValueError(f"{label} does not belong to Case {case_id}")


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


__all__ = [
    "CASE_EVALUATION_SCHEMA",
    "RUBRIC_EVALUATION_SCHEMA",
    "bind_case_evaluation",
    "bind_rubric_evaluation",
]
