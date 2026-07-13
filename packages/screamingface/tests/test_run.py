"""Run — the payoff read-out (score / baseline / gain).

FEATURE: quickstart step 5 — read the gain over the best single model.
"""

from __future__ import annotations

import pytest

import screamingface as sf

IDS = ["anthropic/claude-opus-4.8", "google/gemini-2.5-pro", "openai/gpt-5"]


@pytest.fixture(scope="module")
def run() -> sf.Run:
    fusion = sf.Fusion("fusion", models=IDS, reduce="majority_vote", judge=IDS[0])
    return fusion.evaluate("gpqa", first=20, seed=0)


class TestMetrics:
    def test_score_is_fusion_accuracy_percent(self, run):
        correct = sum(1 for q in run.result.question_results if q.correct)
        assert run.score == pytest.approx(100.0 * correct / run.sample_size, abs=0.05)

    def test_baseline_is_best_single_model(self, run):
        best = max(m.accuracy for m in run.result.model_results)
        assert run.baseline == pytest.approx(best, abs=0.05)

    def test_gain_is_score_minus_baseline(self, run):
        # INVARIANT: gain = score − baseline, always — the headline number.
        assert run.gain == pytest.approx(run.score - run.baseline, abs=0.05)

    def test_metrics_are_rounded_to_tenths(self, run):
        for v in (run.score, run.baseline, run.gain):
            assert v == round(v, 1)

    def test_cost_is_positive_and_rounded(self, run):
        assert run.cost > 0
        assert run.cost == round(run.cost, 4)


class TestIdentity:
    def test_seed_and_sample_size_are_reported(self, run):
        assert run.seed == 0
        assert run.sample_size == 20
        assert run.benchmark_name == "GPQA Diamond"

    def test_run_url_extends_recipe_with_run_params(self, run):
        # INVARIANT I6: the recipe is the identity; a run pins benchmark+n+seed on it.
        assert run.url.startswith(run.fusion.url)
        assert "benchmark=gpqa" in run.url
        assert "seed=0" in run.url

    def test_repr_shows_the_readout(self, run):
        r = repr(run)
        assert "fusion" in r and "GPQA Diamond" in r
        assert "score=" in r and "gain=" in r and "cost=$" in r
