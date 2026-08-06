"""Shared integrity and serialization for compiled Operation projections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from screamingface.operation import OperationInfo


class _FailureReference(Protocol):
    @property
    def operation_id(self) -> str | None: ...


class _MemberReference(Protocol):
    @property
    def operation_id(self) -> str: ...

    @property
    def failures(self) -> Sequence[_FailureReference] | None: ...


def _operation_dict(operation: OperationInfo) -> dict[str, object]:
    return {
        "id": operation.id,
        "kind": operation.kind,
        "label": operation.label,
        "depends_on": list(operation.depends_on),
    }


def _require_operation_references(
    operations: tuple[OperationInfo, ...],
    members: Sequence[_MemberReference],
    failures: Sequence[_FailureReference],
) -> None:
    known = {operation.id for operation in operations}
    references = [member.operation_id for member in members]
    references.extend(
        failure.operation_id for failure in failures if failure.operation_id is not None
    )
    for member in members:
        if member.failures is not None:
            references.extend(
                failure.operation_id
                for failure in member.failures
                if failure.operation_id is not None
            )
    if unknown := sorted(set(references) - known):
        raise ValueError(f"Candidate result references unknown Operation ID {unknown[0]!r}")


__all__: list[str] = []
