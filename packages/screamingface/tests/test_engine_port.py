"""The EngineBackend port and its v0.1 adapter, SimulatedBackend.

INVARIANT (spec §2): the port is the seam where real inference (OME-296)
plugs in — the SimulatedBackend must be swappable for any conforming adapter.
"""

from __future__ import annotations

import pytest

from screamingface.catalog import BENCHMARKS
from screamingface.datasets import load_benchmark
from screamingface.engine import Answer, EngineBackend, SimulatedBackend, hash01
from screamingface.models import get_model


def test_simulated_backend_conforms_to_port():
    # INVARIANT: structural conformance — checked by the type system, not duck luck.
    _: EngineBackend = SimulatedBackend()


def test_hash01_is_deterministic_and_bounded():
    vals = [hash01(0, "x", i) for i in range(100)]
    assert vals == [hash01(0, "x", i) for i in range(100)]
    assert all(0.0 <= v < 1.0 for v in vals)
    assert len(set(vals)) > 50  # spreads, not constant


class TestAnswer:
    def test_answer_fields_are_populated(self):
        bench = load_benchmark("gpqa", n=3, seed=0)
        model = get_model("an-1")
        ans = SimulatedBackend().answer(model, bench.questions[0], bench.spec, seed=0)
        assert isinstance(ans, Answer)
        assert ans.choice and ans.text and ans.reasoning
        assert ans.latency_ms > 0 and ans.tokens_in > 0 and ans.tokens_out > 0
        assert ans.cost > 0

    def test_answer_is_deterministic(self):
        bench = load_benchmark("gpqa", n=3, seed=0)
        model = get_model("an-1")
        a = SimulatedBackend().answer(model, bench.questions[0], bench.spec, seed=0)
        b = SimulatedBackend().answer(model, bench.questions[0], bench.spec, seed=0)
        assert a == b

    def test_correct_flag_matches_gold(self):
        bench = load_benchmark("gpqa", n=10, seed=0)
        model = get_model("an-1")
        backend = SimulatedBackend()
        for q in bench.questions:
            ans = backend.answer(model, q, bench.spec, seed=0)
            assert ans.correct == (ans.choice == q.gold_key)


class TestAccuracyModel:
    def test_accuracy_clipped_to_sane_range(self):
        backend = SimulatedBackend()
        for spec in BENCHMARKS.values():
            for mid in ("an-1", "hf-2"):
                acc = backend.accuracy(get_model(mid), spec, seed=0)
                assert 0.02 <= acc <= 0.98

    def test_stronger_model_scores_higher_on_average(self):
        # WHY: ability must actually drive the simulation — an-1 (38.4) vs hf-2 (14.5).
        bench = load_benchmark("gpqa", n=200, seed=0)
        backend = SimulatedBackend()
        totals = {}
        for mid in ("an-1", "hf-2"):
            m = get_model(mid)
            totals[mid] = sum(backend.answer(m, q, bench.spec, 0).correct for q in bench)
        assert totals["an-1"] > totals["hf-2"]
