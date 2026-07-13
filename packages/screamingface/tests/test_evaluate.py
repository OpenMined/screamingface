"""fusion.evaluate — deterministic runs over real benchmark questions.

INVARIANT (spec I1): same (fusion, benchmark, first, seed) → identical run.
INVARIANT (spec I2): each model's marginal accuracy tracks its ability
regardless of the correlation knob (honest lift).
"""

from __future__ import annotations

import pytest

import screamingface as sf
from screamingface.datasets import load_benchmark
from screamingface.engine import SimulatedBackend

IDS = ["anthropic/claude-opus-4.8", "google/gemini-2.5-pro", "openai/gpt-5"]


def _fusion() -> sf.Fusion:
    return sf.Fusion("fusion", models=IDS, reduce="majority_vote", judge=IDS[0])


class TestDeterminism:
    def test_same_seed_same_run(self):
        r1 = _fusion().evaluate("gpqa", first=20, seed=0)
        r2 = _fusion().evaluate("gpqa", first=20, seed=0)
        assert (r1.score, r1.baseline, r1.gain, r1.cost) == (
            r2.score,
            r2.baseline,
            r2.gain,
            r2.cost,
        )

    def test_different_seed_differs_somewhere(self):
        # WHY: not every metric must move, but two seeds over 20 GPQA questions
        # producing byte-identical per-question outcomes would mean seed is dead.
        r1 = _fusion().evaluate("gpqa", first=20, seed=0)
        r2 = _fusion().evaluate("gpqa", first=20, seed=7)
        q1 = [q.final_choice for q in r1.result.question_results]
        q2 = [q.final_choice for q in r2.result.question_results]
        assert q1 != q2

    def test_first_controls_sample_size(self):
        run = _fusion().evaluate("gpqa", first=5, seed=0)
        assert run.sample_size == 5


class TestBenchmarkLookup:
    def test_accepts_id_and_display_name(self):
        by_id = _fusion().evaluate("gpqa", first=5, seed=0)
        by_name = _fusion().evaluate("GPQA Diamond", first=5, seed=0)
        assert by_id.score == by_name.score
        assert by_id.benchmark_name == "GPQA Diamond"

    def test_unknown_benchmark_raises(self):
        with pytest.raises(KeyError, match="[Uu]nknown benchmark"):
            _fusion().evaluate("nope", first=5, seed=0)

    def test_empty_fusion_cannot_evaluate(self):
        f = sf.Fusion("empty")
        with pytest.raises(ValueError, match="empty"):
            f.evaluate("gpqa", first=5, seed=0)


class TestHonestLift:
    def test_marginal_accuracy_is_correlation_invariant(self):
        # INVARIANT I2: correlation reshuffles WHICH questions a model gets right,
        # never HOW MANY (in expectation). With n=200 the realized accuracy under
        # correlation 0.0 and 0.9 must stay within a few points of each other.
        bench = load_benchmark("gpqa", n=200, seed=0)
        model = sf.models.get(IDS[0])
        spec = bench.spec
        for lo, hi in [(0.0, 0.9)]:
            acc = {}
            for corr in (lo, hi):
                backend = SimulatedBackend(correlation=corr)
                correct = sum(
                    backend.answer(model, q, spec, seed=0).correct for q in bench.questions
                )
                acc[corr] = correct / len(bench.questions)
            assert abs(acc[lo] - acc[hi]) < 0.12

    def test_backend_port_is_the_only_answer_path(self, recording_backend):
        # INVARIANT (spec §2): every answer flows through the EngineBackend port.
        bench = load_benchmark("gpqa", n=5, seed=0)
        run = _fusion().evaluate(bench, seed=0, backend=recording_backend)
        assert run.sample_size == 5
        assert len(recording_backend.calls) == 5 * len(IDS)
