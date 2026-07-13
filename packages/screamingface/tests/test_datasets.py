"""Benchmark loading — real questions, offline-first, deterministic subsampling.

WHY offline-first (deviation from the prototype's hub-first order): the executed
quickstart notebook must be reproducible on GitHub/Colab without network or HF
terms-acceptance; the Hub is opt-in via offline=False.
"""

from __future__ import annotations

import pytest

from screamingface.datasets import load_benchmark


class TestLoad:
    def test_bundled_gpqa_loads_offline(self):
        bench = load_benchmark("gpqa", n=20, seed=0)
        assert bench.name == "GPQA Diamond"
        assert len(bench) == 20
        assert bench.source == "offline-sample"

    def test_questions_are_real_mcqs(self):
        bench = load_benchmark("gpqa", n=5, seed=0)
        for q in bench:
            assert q.kind == "mcq"
            assert q.prompt and len(q.options) >= 2
            assert 0 <= q.gold_index < len(q.options)
            assert q.gold_key  # canonical voting key (a letter)

    def test_subsample_is_deterministic_per_seed(self):
        a = [q.id for q in load_benchmark("gpqa", n=10, seed=3)]
        b = [q.id for q in load_benchmark("gpqa", n=10, seed=3)]
        c = [q.id for q in load_benchmark("gpqa", n=10, seed=4)]
        assert a == b
        assert a != c

    def test_n_larger_than_bundle_returns_everything(self):
        bench = load_benchmark("gpqa", n=10_000, seed=0)
        assert len(bench) > 0
        assert len(bench) < 10_000

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError, match="[Uu]nknown benchmark"):
            load_benchmark("nope", n=5, seed=0)
