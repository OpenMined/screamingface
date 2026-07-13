"""sf.Fusion — composition and the shareable recipe.

FEATURE: compose a fusion (quickstart step 3).
INVARIANT (spec I3): the judge must be one of the fusion's members.
INVARIANT (spec I6): `fusion.url` carries the full composition — the recipe IS the identity.
"""

from __future__ import annotations

import pytest

import screamingface as sf

IDS = [
    "anthropic/claude-opus-4.8",
    "google/gemini-2.5-pro",
    "openai/gpt-5",
]


class TestConstruction:
    def test_basic_construction(self):
        f = sf.Fusion("fusion", models=IDS, reduce="majority_vote", judge=IDS[0])
        assert f.name == "fusion"
        assert f.models == IDS
        assert f.judge == IDS[0]

    def test_name_is_slugified(self):
        assert sf.Fusion("My Fusion", models=IDS[:1]).name == "my-fusion"

    def test_duplicate_members_are_deduped(self):
        f = sf.Fusion("f", models=[IDS[0], IDS[0], IDS[1]])
        assert f.models == [IDS[0], IDS[1]]

    def test_judge_must_be_member(self):
        # INVARIANT I3 — validated at construction, not first use.
        with pytest.raises(ValueError, match="judge"):
            sf.Fusion("f", models=IDS[:2], judge=IDS[2])

    def test_unknown_reduce_strategy_raises(self):
        with pytest.raises(ValueError, match="reduce"):
            sf.Fusion("f", models=IDS, reduce="quantum_entangle")

    def test_unknown_model_raises_with_hint(self):
        with pytest.raises(KeyError, match="models.list"):
            sf.Fusion("f", models=["nope/nothing"])

    @pytest.mark.parametrize("strategy", ["majority_vote", "weighted_avg", "best_of_n", "merge"])
    def test_all_builtin_strategies_accepted(self, strategy):
        assert sf.Fusion("f", models=IDS, reduce=strategy)


class TestUrl:
    def test_url_shape(self):
        # STORY: as a researcher I paste one string to share my whole recipe.
        f = sf.Fusion("fusion", models=IDS, reduce="majority_vote", judge=IDS[0])
        assert f.url == (
            "url4://fusion?models=anthropic/claude-opus-4.8+google/gemini-2.5-pro"
            "+openai/gpt-5&reduce=majority_vote&loop=parallel"
            "&judge=anthropic/claude-opus-4.8"
        )

    def test_url_omits_judge_when_unset(self):
        f = sf.Fusion("f", models=IDS[:2])
        assert "judge=" not in f.url
        assert "reduce=majority_vote" in f.url  # the default strategy is explicit

    def test_url_never_contains_a_key(self, monkeypatch):
        # INVARIANT I4 — keys never escape into recipes.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret-1234")
        sf.connect("anthropic")
        f = sf.Fusion("f", models=IDS, judge=IDS[0])
        assert "sk-super-secret" not in f.url
        assert "1234" not in f.url
