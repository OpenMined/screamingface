"""Small built-in progress observer driven exclusively by public Events."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TextIO

from screamingface.events import Event, Log, Span, Started, Terminated


def _progress_observer(
    requested: bool | None,
    *,
    stream: TextIO | None = None,
) -> Callable[[Event], None] | None:
    selected_stream = sys.stderr if stream is None else stream
    if requested is False:
        return None
    if requested is None and not (_in_notebook() or selected_stream.isatty()):
        return None
    return _ProgressObserver(selected_stream)


class _ProgressObserver:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def __call__(self, event: Event) -> None:
        message = _message(event)
        if message is not None:
            self._stream.write(f"ScreamingFace · {message}\n")
            self._stream.flush()


def _message(event: Event) -> str | None:
    message: str | None = None
    if isinstance(event, Started):
        message = "Run started"
    elif isinstance(event, Log):
        message = event.body or None
    elif isinstance(event, Span):
        message = f"{event.operation}: {event.name}"
    elif isinstance(event, Terminated):
        message = f"Run {event.status.replace('_', ' ')}"
    return message


def _in_notebook() -> bool:
    return "ipykernel" in sys.modules


__all__: list[str] = []
