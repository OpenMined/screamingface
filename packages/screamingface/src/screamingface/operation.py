"""Immutable public operation projections attached to Candidate results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, init=False)
class OperationInfo:
    """One logical operation in a compiled Candidate URL4 DAG."""

    id: str
    kind: str
    label: str
    depends_on: tuple[str, ...]

    def __init__(
        self,
        *,
        id: str,
        kind: str,
        label: str,
        depends_on: Sequence[str] = (),
    ) -> None:
        operation_id = _nonblank(id, "Operation id")
        dependencies = _unique_texts(depends_on, "Operation depends_on", allow_empty=True)
        if operation_id in dependencies:
            raise ValueError("an Operation cannot depend on itself")
        object.__setattr__(self, "id", operation_id)
        object.__setattr__(self, "kind", _nonblank(kind, "Operation kind"))
        object.__setattr__(self, "label", _nonblank(label, "Operation label"))
        object.__setattr__(self, "depends_on", dependencies)


def _operation_dag(values: Sequence[OperationInfo]) -> tuple[OperationInfo, ...]:
    operations = _operation_values(values)
    _require_acyclic(operations)
    return operations


def _operation_values(values: Sequence[OperationInfo]) -> tuple[OperationInfo, ...]:
    try:
        operations = tuple(values)
    except TypeError as exc:
        raise TypeError("Candidate operations must be an ordered sequence") from exc
    if not operations:
        raise ValueError("a Candidate requires at least one Operation")
    if any(not isinstance(operation, OperationInfo) for operation in operations):
        raise TypeError("Candidate operations must contain only sf.OperationInfo values")

    operation_ids = tuple(operation.id for operation in operations)
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("Candidate Operation IDs must be unique")
    known_ids = set(operation_ids)
    if unknown := {
        dependency
        for operation in operations
        for dependency in operation.depends_on
        if dependency not in known_ids
    }:
        raise ValueError(f"Candidate Operation has unknown dependency {min(unknown)!r}")
    return operations


def _require_acyclic(operations: tuple[OperationInfo, ...]) -> None:
    # INVARIANT: operation identity, not URL equality, defines the Candidate DAG.
    remaining = {operation.id: set(operation.depends_on) for operation in operations}
    resolved: set[str] = set()
    while ready := {
        operation_id for operation_id, dependencies in remaining.items() if dependencies <= resolved
    }:
        resolved.update(ready)
        for operation_id in ready:
            del remaining[operation_id]
    if remaining:
        raise ValueError("Candidate Operations must form an acyclic DAG; cycle detected")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _unique_texts(
    values: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, str | bytes) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be an ordered sequence of strings")
    selected = tuple(_nonblank(value, label) for value in values)
    if not selected and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    if len(selected) != len(set(selected)):
        raise ValueError(f"{label} must be unique")
    return selected


__all__ = ["OperationInfo"]
