"""FusionCore — a composed set of model slots plus a reduce stage (engine-side).

A fusion runs every question through a **loop stage** (v0.1: `parallel` — every
model answers) and a **reduce stage** (combine the candidates into one final
answer). AIDEV-NOTE: custom reduce/loop Scripts are OME-408-adjacent scope and
deliberately absent here; `reduce()`/`loop()` keep the seam.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Model, resolve

REDUCE_STRATEGIES = {
    "majority_vote": "Judge picks the most common answer",
    "weighted_avg": "Blend answers weighted by confidence",
    "best_of_n": "Judge ranks and selects the top response",
    "merge": "Judge merges every answer into one",
}
LOOP_MODES = {
    "parallel": "Run every model on each question",
}


@dataclass
class Slot:
    """One model's seat in the fusion."""

    model: Model
    system_prompt: str = ""
    weight: float = 0.5

    @property
    def id(self) -> str:
        return self.model.id


class FusionCore:
    def __init__(self, name: str = "untitled-fusion"):
        self.name = name.strip().replace(" ", "-").lower() or "untitled-fusion"
        self.slots: list[Slot] = []
        self.reduce_strategy: str = "majority_vote"
        self.loop_mode: str = "parallel"
        self.judge_model_id: str | None = None

    # ── composition ──────────────────────────────────────────────────────────
    def add(self, model: str | Model, weight: float = 0.5, system: str = "") -> FusionCore:
        """Add a model slot. Re-adding the same model is a no-op."""
        m = resolve(model)
        if not any(s.id == m.id for s in self.slots):
            self.slots.append(Slot(model=m, system_prompt=system, weight=weight))
        return self

    def reduce(
        self, strategy: str = "majority_vote", judge: str | Model | None = None
    ) -> FusionCore:
        """Set the reduce stage: a built-in strategy name, arbitrated by an
        optional `judge` model (which must be a member)."""
        if strategy not in REDUCE_STRATEGIES:
            raise ValueError(
                f"Unknown reduce strategy {strategy!r}. Choose one of {sorted(REDUCE_STRATEGIES)}."
            )
        self.reduce_strategy = strategy
        if judge is not None:
            self.set_judge(judge)
        return self

    def set_judge(self, judge: str | Model) -> FusionCore:
        # INVARIANT (spec I3): the judge must be one of the fusion's members.
        mid = judge.id if isinstance(judge, Model) else judge
        if not any(s.id == mid for s in self.slots):
            raise ValueError(
                f"judge {mid!r} must be one of the fusion's models: {[s.id for s in self.slots]}"
            )
        self.judge_model_id = mid
        return self

    def loop(self, mode: str = "parallel") -> FusionCore:
        """Set the loop stage (v0.1: 'parallel' only)."""
        if mode not in LOOP_MODES:
            raise ValueError(f"Unknown loop mode {mode!r}. Choose one of {sorted(LOOP_MODES)}.")
        self.loop_mode = mode
        return self

    # ── derived views ─────────────────────────────────────────────────────────
    @property
    def models(self) -> list[Model]:
        return [s.model for s in self.slots]

    @property
    def judge(self) -> Model | None:
        if self.judge_model_id is None:
            return None
        return next((s.model for s in self.slots if s.id == self.judge_model_id), None)

    def normalized_weights(self) -> list[float]:
        """Weights over the *non-judge* slots, summing to 1.

        INVARIANT: the judge arbitrates rather than contributes — it is excluded
        from the blend and carries weight 0.
        """
        contributing = [s for s in self.slots if s.id != self.judge_model_id]
        total = sum(s.weight for s in contributing) or 1.0
        return [0.0 if s.id == self.judge_model_id else s.weight / total for s in self.slots]

    def __repr__(self) -> str:
        return (
            f"FusionCore({self.name!r}, {len(self.slots)} models, "
            f"reduce={self.reduce_strategy}, loop={self.loop_mode})"
        )
