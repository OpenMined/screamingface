"""Spec §8 guard: fusion fan-out must execute through the URL4 executor."""

from __future__ import annotations

import pytest

import screamingface as sf
import screamingface.evaluation as evaluation


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def _mock_fusion() -> sf.Fusion:
    sf.setup(mode="mock", interactive=False)
    ids = sf.models.list()
    return sf.Fusion("seam", ids[:3], judge=ids[0])


def test_every_panel_answer_traverses_the_url4_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # INVARIANT: spec §8 — URL4 is the execution seam, not just serialization. Every
    # question is one run_url4 call on the fusion's compiled expression, and every
    # panel answer used for vote/baseline comes from the IO layer it executed.
    fusion = _mock_fusion()
    real_run_url4 = evaluation.run_url4
    recorded: list[tuple[object, evaluation.QuestionIOLayer]] = []

    async def spying_run_url4(expression, *, io, process):
        recorded.append((expression, io))
        return await real_run_url4(expression, io=io, process=process)

    monkeypatch.setattr(evaluation, "run_url4", spying_run_url4)

    run = fusion.evaluate("gpqa", first=4, seed=0)

    assert run.sample_size == 4
    assert len(recorded) == 4
    assert all(expression is fusion.expression for expression, _io in recorded)
    assert all(set(io.answers) == set(fusion.models) for _expression, io in recorded)


def test_a_model_loop_bypassing_url4_produces_no_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # INVARIANT: spec §8 — answers exist only if run_url4 drives the CompletionPort;
    # a direct Python model loop plus vote cannot satisfy the evaluator.
    fusion = _mock_fusion()

    async def bypassing_run_url4(expression, *, io, process):
        del expression, io, process
        return ""

    monkeypatch.setattr(evaluation, "run_url4", bypassing_run_url4)

    run = fusion.evaluate("gpqa", first=2, seed=0)

    assert run.score == 0.0
    assert run.baseline == 0.0
    assert run.incomplete == 2
