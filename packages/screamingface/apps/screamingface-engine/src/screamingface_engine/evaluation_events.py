"""Evaluation-scoped progress events emitted by ScreamingFace-owned URL4 routes."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

type EventStage = Literal["dataset", "model", "grading", "aggregating"]
type EventStatus = Literal["started", "completed"]
type EventSink = Callable[[dict[str, object]], None]

_SINK: ContextVar[EventSink | None] = ContextVar(
    "screamingface_evaluation_event_sink", default=None
)


@contextmanager
def evaluation_event_sink(sink: EventSink) -> Iterator[None]:
    """Bind one event sink while an evaluation task and its children are created."""

    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)


def emit_progress(stage: EventStage, status: EventStatus, label: str) -> None:
    """Emit one safe presentation event when evaluation streaming is active."""

    sink = _SINK.get()
    if sink is not None:
        sink({"stage": stage, "status": status, "label": label})


__all__ = ["emit_progress", "evaluation_event_sink"]
