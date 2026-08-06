"""Task-local model outcomes shared by connectors and orchestration adapters."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    """Literal terminal fields reported by one provider round trip."""

    finish_reason: str | None
    refusal: str | None


type OutcomeRecorder = list[ModelOutcome]

_recorders: contextvars.ContextVar[tuple[OutcomeRecorder, ...]] = contextvars.ContextVar(
    "url4_cloud_model_outcome_recorders", default=()
)
_ERROR_OUTCOME_ATTRIBUTE = "_url4_cloud_model_outcome"


@contextmanager
def capture_model_outcomes() -> Iterator[OutcomeRecorder]:
    """Capture outcomes in this scope without hiding them from an enclosing scope."""

    recorder: OutcomeRecorder = []
    token = _recorders.set((*_recorders.get(), recorder))
    try:
        yield recorder
    finally:
        _recorders.reset(token)


def record_model_outcome(finish_reason: str | None, refusal: str | None) -> None:
    """Publish one already-observed provider outcome to every active scope."""

    outcome = ModelOutcome(finish_reason=finish_reason, refusal=refusal)
    for recorder in _recorders.get():
        recorder.append(outcome)


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
]
