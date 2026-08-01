"""Shared integrity and serialization for Engine-derived Operation projections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from screamingface._evaluation.model import Operation


class _FailureReference(Protocol):
    @property
    def operation_id(self) -> str: ...


class _MemberReference(Protocol):
    @property
    def operation_id(self) -> str: ...

    @property
    def failures(self) -> Sequence[_FailureReference]: ...


def _operation_dict(operation: Operation) -> dict[str, object]:
    return {
        "id": operation.id,
        "kind": operation.kind,
        "label": operation.label,
        "depends_on": list(operation.depends_on),
    }


def _require_operation_references(
    operations: tuple[Operation, ...],
    members: Sequence[_MemberReference],
    failures: Sequence[_FailureReference],
) -> None:
    known = {operation.id for operation in operations}
    references = [member.operation_id for member in members]
    references.extend(failure.operation_id for failure in failures)
    for member in members:
        references.extend(failure.operation_id for failure in member.failures)
    if unknown := sorted(set(references) - known):
        raise ValueError(f"Candidate result references unknown Operation ID {unknown[0]!r}")


__all__: list[str] = []
