"""The reduce stage: combine per-model candidate answers into one final answer.

INVARIANT (spec I2): strategies operate on the models' *canonical* answers (an
option letter for multiple-choice, the answer string for free-text), so the
combination is real voting math — fusion lift is emergent, never a bonus.
"""

from __future__ import annotations

from collections import defaultdict

from .engine import Answer
from .fusion_core import FusionCore

_NOTES = {
    "majority_vote": "majority vote",
    "weighted_avg": "weighted vote",
    "merge": "merge (judge synthesis)",  # WHY: judge synthesis over discrete answers = majority
}


def reduce_answers(
    fusion: FusionCore, answers: list[Answer], weights: list[float]
) -> tuple[str, str]:
    """Return ``(final_choice, note)`` for one question.

    `answers` is aligned with ``fusion.slots``; `weights` are the normalized
    non-judge weights (judge weight is 0). `note` is a short human-readable
    description of how the answer was chosen.
    """
    slots = fusion.slots
    judge_idx = next((i for i, s in enumerate(slots) if s.id == fusion.judge_model_id), None)
    # contributing (non-judge) indices; a judge-only fusion still answers
    contrib = [i for i in range(len(slots)) if i != judge_idx] or list(range(len(slots)))

    strategy = fusion.reduce_strategy
    if strategy == "best_of_n":
        return _best_choice(fusion, answers, contrib), "best-of-N (judge picks strongest model)"
    choice = _vote(
        fusion, answers, weights, contrib, judge_idx, weighted=(strategy == "weighted_avg")
    )
    return choice, _NOTES[strategy]


def _best_choice(fusion: FusionCore, answers: list[Answer], contrib: list[int]) -> str:
    """The highest-ability contributing model's answer."""
    i = max(contrib, key=lambda i: fusion.slots[i].model.ability)
    return answers[i].choice


def _vote(
    fusion: FusionCore,
    answers: list[Answer],
    weights: list[float],
    contrib: list[int],
    judge_idx: int | None,
    weighted: bool,
) -> str:
    tally: dict[str, float] = defaultdict(float)
    for i in contrib:
        tally[answers[i].choice] += weights[i] if weighted else 1.0
    top = max(tally.values())
    winners = [c for c, v in tally.items() if abs(v - top) < 1e-9]
    if len(winners) == 1:
        return winners[0]
    # tie-break: prefer the judge's own answer, else the best model's answer
    judge_choice = answers[judge_idx].choice if judge_idx is not None else None
    if judge_choice in winners:
        return judge_choice
    best = _best_choice(fusion, answers, contrib)
    return best if best in winners else sorted(winners)[0]
