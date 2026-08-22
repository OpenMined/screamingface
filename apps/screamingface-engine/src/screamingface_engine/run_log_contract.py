"""Dependency-free interface for optional run-scoped structured Logs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol

type LogScalar = str | int | float | bool | None


class StructuredLogEmitter(Protocol):
    """Synchronous, non-blocking submission into one execution's existing bridge."""

    def __call__(self, body: str, attributes: Mapping[str, LogScalar]) -> None: ...


class RunLogScopeFactory(Protocol):
    """The one generic lifecycle operation an observational adapter implements."""

    def open_run_scope(
        self,
        rendered_url4: str,
        emit_structured_log: StructuredLogEmitter,
    ) -> AbstractContextManager[None] | None: ...


__all__ = ["LogScalar", "RunLogScopeFactory", "StructuredLogEmitter"]
