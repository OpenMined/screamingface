"""Dependency-free interface for optional run-scoped structured Logs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol

type LogScalar = str | int | float | bool | None


class StructuredLogEmitter(Protocol):
    """Synchronous, non-blocking submission into one execution's existing bridge.

    Calls must remain on the event-loop thread that received the emitter. Off-thread calls are
    invalid and are ignored by the Runner rather than mutating its non-thread-safe bridge; repeated
    violations produce at most one operator diagnostic per emitter.
    Attribute floats must be finite; non-finite values are rejected as malformed records.
    """

    def __call__(self, body: str, attributes: Mapping[str, LogScalar]) -> None: ...


class RunLogScopeFactory(Protocol):
    """The one generic lifecycle operation an observational adapter implements.

    The returned context manager owns partial-acquisition rollback: when its ``__enter__`` raises,
    it must unwind anything already acquired before re-raising because the Runner will not call
    ``__exit__`` afterward, following Python's context-manager protocol.
    """

    def open_run_scope(
        self,
        rendered_url4: str,
        emit_structured_log: StructuredLogEmitter,
    ) -> AbstractContextManager[None] | None: ...


__all__ = ["LogScalar", "RunLogScopeFactory", "StructuredLogEmitter"]
