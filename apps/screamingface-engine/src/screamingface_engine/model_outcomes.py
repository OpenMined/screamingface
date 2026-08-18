"""Task-local model outcomes shared by connectors and orchestration adapters."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    """Literal terminal fields reported by one provider round trip."""

    finish_reason: str | None
    refusal: str | None


type OutcomeRecorder = list[ModelOutcome]

_recorders: contextvars.ContextVar[tuple[OutcomeRecorder, ...]] = contextvars.ContextVar(
    "screamingface_engine_model_outcome_recorders", default=()
)
_ERROR_OUTCOME_ATTRIBUTE = "_screamingface_engine_model_outcome"


@contextmanager
def capture_model_outcomes(*, isolated: bool = False) -> Iterator[OutcomeRecorder]:
    """Capture outcomes in this scope.

    Ordinary nested scopes also publish into every enclosing recorder. An
    orchestration boundary may request an isolated capture when it is turning
    one nested Recipe into its own typed outcome; otherwise sibling member and
    judge calls would be misattributed to the final selected answer.
    """

    recorder: OutcomeRecorder = []
    active = () if isolated else _recorders.get()
    token = _recorders.set((*active, recorder))
    try:
        yield recorder
    finally:
        _recorders.reset(token)


def record_model_outcome(finish_reason: str | None, refusal: str | None) -> None:
    """Publish one already-observed provider outcome to every active scope."""

    outcome = ModelOutcome(finish_reason=finish_reason, refusal=refusal)
    for recorder in _recorders.get():
        recorder.append(outcome)


def terminal_model_outcome(outcomes: Sequence[ModelOutcome]) -> ModelOutcome:
    """Return the unambiguous outcome describing a composed Recipe result."""

    distinct = set(outcomes)
    return distinct.pop() if len(distinct) == 1 else ModelOutcome(None, None)


def bind_model_outcome(error: BaseException, outcome: ModelOutcome) -> BaseException:
    """Attach the exact provider outcome to the error raised for that round trip."""

    setattr(error, _ERROR_OUTCOME_ATTRIBUTE, outcome)
    return error


def model_outcome_from_error(error: BaseException) -> ModelOutcome | None:
    """Return an outcome bound by the Connector, without depending on its error type."""

    outcome = getattr(error, _ERROR_OUTCOME_ATTRIBUTE, None)
    return outcome if isinstance(outcome, ModelOutcome) else None


__all__ = [
    "ModelOutcome",
    "bind_model_outcome",
    "capture_model_outcomes",
    "model_outcome_from_error",
    "record_model_outcome",
    "terminal_model_outcome",
]
