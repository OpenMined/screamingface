"""Task-local execution provenance for one complete Candidate Recipe."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from screamingface_engine.benchmarks.contract import CorrectiveExecution
from url4.core.errors import ResolutionError

type ExecutionRecorder = list[CorrectiveExecution]

_recorders: contextvars.ContextVar[tuple[ExecutionRecorder, ...]] = contextvars.ContextVar(
    "screamingface_engine_candidate_execution_recorders", default=()
)


@contextmanager
def capture_candidate_executions(*, isolated: bool = False) -> Iterator[ExecutionRecorder]:
    """Capture provenance emitted by the Recipe's terminal orchestration boundary."""

    recorder: ExecutionRecorder = []
    active = () if isolated else _recorders.get()
    token = _recorders.set((*active, recorder))
    try:
        yield recorder
    finally:
        _recorders.reset(token)


def record_candidate_execution(execution: CorrectiveExecution) -> None:
    """Publish one already-decided execution outcome to every active scope."""

    for recorder in _recorders.get():
        recorder.append(execution)


def terminal_candidate_execution(
    executions: Sequence[CorrectiveExecution],
) -> CorrectiveExecution | None:
    """Return the one unambiguous execution outcome for the complete Recipe."""

    if not executions:
        return None
    first = executions[0]
    if all(execution == first for execution in executions[1:]):
        return first
    raise ResolutionError(
        "Candidate Recipe emitted ambiguous execution provenance",
        code="candidate_contract_error",
        permanent=True,
    )


__all__ = [
    "capture_candidate_executions",
    "record_candidate_execution",
    "terminal_candidate_execution",
]
