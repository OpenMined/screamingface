"""Spec §8 guard: fusion fan-out must execute through the public URL4 node."""

from __future__ import annotations

import pytest
from url4 import Url4Node, Url4Result, render

import screamingface as sf
import screamingface.evaluation as evaluation


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def _mock_fusion() -> sf.Fusion:
    sf.setup(mode="mock", interactive=False)
    ids = sf.models.list()
    return sf.Fusion("seam", ids[:3], judge=ids[0])


def test_every_panel_answer_traverses_a_public_url4_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # INVARIANT: spec §8 — URL4 is the execution seam, not just serialization.
    # Every question is evaluated by the public Url4Node facade, whose outbound
    # I/O layer produces every panel answer used for both vote and baseline.
    fusion = _mock_fusion()
    recorded: list[tuple[object, evaluation.QuestionIOLayer, str]] = []

    class SpyingUrl4Node(Url4Node):
        async def evaluate(self, expression, *, env=None):
            result = await super().evaluate(expression, env=env)
            assert isinstance(self._outbound, evaluation.QuestionIOLayer)
            recorded.append((expression, self._outbound, result.request))
            return result

    monkeypatch.setattr(evaluation, "Url4Node", SpyingUrl4Node)

    run = fusion.evaluate("gpqa", first=4, seed=0)

    assert run.sample_size == 4
    assert len(recorded) == 4
    assert all(expression is fusion.expression for expression, _io, _request in recorded)
    assert all(set(io.answers) == set(fusion.models) for _expression, io, _request in recorded)
    assert all(request == fusion.url4 for _expression, _io, request in recorded)


def test_a_model_loop_bypassing_url4_produces_no_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # INVARIANT: spec §8 — answers exist only if Url4Node drives the CompletionPort;
    # a direct Python model loop plus vote cannot satisfy the evaluator.
    fusion = _mock_fusion()

    class BypassingUrl4Node(Url4Node):
        async def evaluate(self, expression, *, env=None):
            del env
            request = expression if isinstance(expression, str) else render(expression)
            return Url4Result(text="", request=request)

    monkeypatch.setattr(evaluation, "Url4Node", BypassingUrl4Node)

    run = fusion.evaluate("gpqa", first=2, seed=0)

    assert run.score == 0.0
    assert run.baseline == 0.0
    assert run.incomplete == 2
