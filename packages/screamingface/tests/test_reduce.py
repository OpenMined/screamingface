"""Reduce strategies — real voting math over per-model answers.

FEATURE: the reduce stage is where fusion lift comes from (spec I2: the gain
emerges from combining answers, never from a hard-coded bonus).
"""

from __future__ import annotations

import pytest

from screamingface.engine import Answer
from screamingface.fusion_core import FusionCore
from screamingface.reduce import reduce_answers


def _answer(choice: str) -> Answer:
    return Answer(
        choice=choice, text=choice, correct=False, reasoning="",
        latency_ms=0, tokens_in=0, tokens_out=0, cost=0.0,
    )


def _core(model_ids, judge=None, strategy="majority_vote", weights=None) -> FusionCore:
    core = FusionCore("t")
    for i, mid in enumerate(model_ids):
        core.add(mid, weight=(weights[i] if weights else 0.5))
    core.reduce(strategy, judge=judge)
    return core


# WHY: short catalog ids keep the voting-table tests readable; the studio layer
# owns the provider/model alias scheme and is tested separately.
M3 = ["an-1", "dm-1", "oa-1"]


class TestMajorityVote:
    def test_majority_wins(self):
        core = _core(M3)
        choice, note = reduce_answers(core, [_answer("A"), _answer("A"), _answer("B")],
                                      core.normalized_weights())
        assert choice == "A"
        assert "majority" in note

    def test_tie_prefers_judge_answer(self):
        core = _core(M3, judge="an-1")
        # judge (an-1) says B; dm-1 says A; oa-1 abstains into C → 3-way tie
        choice, _ = reduce_answers(core, [_answer("B"), _answer("A"), _answer("C")],
                                   core.normalized_weights())
        assert choice == "B"


class TestWeightedAvg:
    def test_heavier_weight_wins(self):
        core = _core(M3, strategy="weighted_avg", weights=[0.8, 0.1, 0.1])
        choice, _ = reduce_answers(core, [_answer("B"), _answer("A"), _answer("A")],
                                   core.normalized_weights())
        # 0.8 for B beats 0.2 combined for A
        assert choice == "B"


class TestBestOfN:
    def test_picks_highest_ability_member(self):
        core = _core(M3, strategy="best_of_n")
        # an-1 has the highest ability in the catalog → its answer wins
        choice, _ = reduce_answers(core, [_answer("C"), _answer("A"), _answer("A")],
                                   core.normalized_weights())
        assert choice == "C"


class TestMerge:
    def test_merge_reduces_to_consensus(self):
        core = _core(M3, strategy="merge")
        choice, _ = reduce_answers(core, [_answer("A"), _answer("A"), _answer("B")],
                                   core.normalized_weights())
        assert choice == "A"


class TestJudgeExclusion:
    def test_judge_does_not_contribute_a_vote(self):
        # INVARIANT: the judge arbitrates, it does not vote (weight 0).
        core = _core(M3, judge="an-1")
        weights = core.normalized_weights()
        assert weights[0] == 0.0
        assert weights[1] + weights[2] == pytest.approx(1.0)
        # judge says A, but both voters say B → B wins despite the judge
        choice, _ = reduce_answers(core, [_answer("A"), _answer("B"), _answer("B")], weights)
        assert choice == "B"
