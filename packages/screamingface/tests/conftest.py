"""Shared fixtures for the screamingface test suite.

`RecordingBackend` mirrors url4's `RecordingIOLayer` convention: a structurally
conforming `EngineBackend` that delegates to the real `SimulatedBackend` while
recording every (model, question) it was asked — used to prove the evaluate
loop drives everything through the port.
"""

from __future__ import annotations

import pytest

from screamingface.engine import Answer, EngineBackend, SimulatedBackend


class RecordingBackend:
    """Delegating EngineBackend that records every answer request."""

    def __init__(self) -> None:
        self._inner = SimulatedBackend()
        self.calls: list[tuple[str, str]] = []  # (model_id, question_id)

    def answer(self, model, question, benchmark, seed: int) -> Answer:
        self.calls.append((model.id, question.id))
        return self._inner.answer(model, question, benchmark, seed)

    def synth_reasoning(self, seed: int, question) -> str:
        return self._inner.synth_reasoning(seed, question)


# INVARIANT: RecordingBackend structurally conforms to the EngineBackend port.
_: EngineBackend = RecordingBackend()


@pytest.fixture
def recording_backend() -> RecordingBackend:
    return RecordingBackend()
