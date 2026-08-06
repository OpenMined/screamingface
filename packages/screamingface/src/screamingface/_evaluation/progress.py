"""Small built-in progress observer driven exclusively by public Events."""

from __future__ import annotations

import sys
import unicodedata
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
            self._stream.write(f"ScreamingFace · {_terminal_text(message)}\n")
            self._stream.flush()


def _message(event: Event) -> str | None:
    message: str | None = None
    if isinstance(event, Started):
        message = "Run started"
    elif isinstance(event, Log):
        message = event.body or None
    elif isinstance(event, Span):
        message = _model_message(event)
    elif isinstance(event, Terminated):
        message = f"Run {event.status.replace('_', ' ')}"
    return message


def _model_message(event: Span) -> str | None:
    """Render paid model work while hiding URL4's structural execution spans."""

    if event.request_model is None:
        return None
    outcome = (
        "refused"
        if event.refusal is not None
        else "failed"
        if event.status == "error"
        else "completed"
    )
    parts = [f"Model {outcome}", event.request_model]
    if event.start is not None and event.end is not None:
        parts.append(_duration((event.end - event.start).total_seconds()))
    if event.input_tokens is not None or event.output_tokens is not None:
        input_tokens = "?" if event.input_tokens is None else f"{event.input_tokens:,}"
        output_tokens = "?" if event.output_tokens is None else f"{event.output_tokens:,}"
        parts.append(f"{input_tokens} in / {output_tokens} out")
    if event.finish_reasons:
        parts.append(" → ".join(event.finish_reasons))
    return " · ".join(parts)


def _duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 10:
        return f"{seconds:.1f}s"
    return f"{seconds:.0f}s"


def _terminal_text(value: str) -> str:
    """Keep untrusted Engine log text on one inert terminal line."""

    inert = "".join(
        " " if unicodedata.category(character).startswith("C") else character for character in value
    )
    return " ".join(inert.split())


def _in_notebook() -> bool:
    return "ipykernel" in sys.modules


__all__: list[str] = []
