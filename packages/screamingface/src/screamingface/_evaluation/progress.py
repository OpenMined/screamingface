"""Small built-in progress observer driven exclusively by public Events."""

from __future__ import annotations

import logging
import sys
import unicodedata
from collections.abc import Callable
from typing import TextIO

from screamingface.events import BenchmarkProgress, Event, Log, Span, Started, Terminated

_logger = logging.getLogger(__name__)


def _progress_observer(
    requested: bool | None,
    *,
    stream: TextIO | None = None,
    total_candidates: int | None = None,
    benchmark: str | None = None,
    case_count: int | None = None,
    candidate_models: tuple[str, ...] = (),
    candidate_urls: tuple[str, ...] = (),
    candidate_names: tuple[str, ...] = (),
    check_disclosure: str | None = None,
) -> Callable[[Event], None] | None:
    selected_stream = sys.stderr if stream is None else stream
    in_notebook = _in_notebook()
    enabled = requested is not False and (
        requested is not None or in_notebook or selected_stream.isatty()
    )
    # In a notebook the live panel is preferred; text remains the fallback everywhere.
    rich = (
        _notebook_observer(
            total_candidates,
            benchmark,
            case_count,
            candidate_models,
            candidate_urls,
            candidate_names,
            check_disclosure,
        )
        if enabled and in_notebook
        else None
    )
    # The paid-check disclosure must never be silent (OME-845): the panel is its calm
    # carrier, and every path that ends without a panel — progress off, headless, panel
    # construction failure — falls back to the Python warning the panel replaced.
    if check_disclosure is not None and rich is None:
        import warnings

        from screamingface.warnings import EvaluationWarning

        warnings.warn(check_disclosure, EvaluationWarning, stacklevel=5)
    if not enabled:
        return None
    return _ProgressObserver(selected_stream) if rich is None else rich


def _notebook_observer(
    total_candidates: int | None,
    benchmark: str | None,
    case_count: int | None,
    candidate_models: tuple[str, ...],
    candidate_urls: tuple[str, ...],
    candidate_names: tuple[str, ...],
    check_disclosure: str | None = None,
) -> Callable[[Event], None] | None:
    """The live panel, or None when it cannot be built (text progress then carries it).

    Building a widget touches ipywidgets' comm layer, which can fail for reasons well
    beyond a missing extra. Progress is decorative and must never take down paid Engine
    work, so ANY construction failure degrades to the text observer rather than raising.
    """

    try:
        from screamingface._ui.evaluation_view import _NotebookEvaluationView

        return _NotebookEvaluationView(
            total_candidates,
            benchmark,
            case_count,
            candidate_models,
            candidate_urls,
            candidate_names,
            check_disclosure=check_disclosure,
        )
    except Exception:
        _logger.debug("Rich notebook progress unavailable; using text progress", exc_info=True)
        return None


class _ProgressObserver:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._benchmark_progress: dict[str, BenchmarkProgress] = {}

    def __call__(self, event: Event) -> None:
        if isinstance(event, BenchmarkProgress):
            self._benchmark_progress[event.run_id] = event
        message = _message(event, benchmark_progress=self._benchmark_progress.get(event.run_id))
        if message is not None:
            self._stream.write(f"ScreamingFace · {_terminal_text(message)}\n")
            self._stream.flush()


def _message(
    event: Event,
    *,
    benchmark_progress: BenchmarkProgress | None = None,
) -> str | None:
    message: str | None = None
    if isinstance(event, Started):
        message = "Evaluation started"
    elif isinstance(event, BenchmarkProgress):
        score = _benchmark_score_text(event)
        message = (
            f"Cases {event.complete_cases}/{event.total_cases} complete · "
            f"{event.scored_cases} scored · {score}"
        )
    elif isinstance(event, Log):
        message = event.body or None
    elif isinstance(event, Span):
        message = _model_message(event)
    elif isinstance(event, Terminated):
        message = _termination_message(event.status, benchmark_progress)
    return message


def _benchmark_score_text(event: BenchmarkProgress) -> str:
    if event.provisional_score is not None:
        label = "score" if event.complete_cases == event.total_cases else "score so far"
        return f"{label} {event.provisional_score:.6g}"
    if event.complete_cases == event.total_cases:
        return "score unavailable"
    return "awaiting first grade"


def _termination_message(
    status: str,
    benchmark_progress: BenchmarkProgress | None = None,
) -> str:
    if status == "succeeded":
        if benchmark_progress is not None and (
            benchmark_progress.complete_cases < benchmark_progress.total_cases
            or benchmark_progress.scored_cases < benchmark_progress.total_cases
        ):
            return "Evaluation incomplete"
        return "Evaluation finished"
    return f"Evaluation {status.replace('_', ' ')}"


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
