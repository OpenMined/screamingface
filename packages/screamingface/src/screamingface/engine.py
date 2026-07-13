"""The EngineBackend port and the v0.1 simulated adapter.

INVARIANT: all answer generation flows through `EngineBackend` — this Protocol
is the seam where real inference (the engine interface, `OME-296`) plugs in as
a second adapter without touching the public API.

The `SimulatedBackend` never calls a real model. For each (model, question)
pair it draws a **deterministic** pseudo-random outcome deciding whether the
model answers correctly, what it answers, and a plausible reasoning trace,
latency, and token cost.

WHY the simulation is honest rather than a toy: a model's correctness is drawn
from a *shared* per-question difficulty term plus a *per-model idiosyncratic*
term, mixed by a `correlation` knob. With low correlation, models make
independent errors — so a majority vote over their answers genuinely recovers
the truth more often than any single model. Fusion lift downstream is an
emergent consequence of real voting math, not a hard-coded bonus.

Everything is seeded: two runs with the same `seed` are byte-for-byte identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .catalog import BenchmarkSpec
from .models import Model

if TYPE_CHECKING:
    from .datasets import Question

LETTERS = [chr(ord("A") + i) for i in range(26)]

# Canned reasoning, ported from the design prototype's REASONING / SYNTH pools.
REASONING = [
    "Let me reason through this. The governing principle fixes a proportional "
    "relationship, so I scale the known quantity directly rather than guessing.",
    "I start by eliminating the options that violate the underlying constraint, "
    "which removes the obvious distractors and leaves one consistent candidate.",
    "Working from the definitions: the standard result applies almost verbatim "
    "here, so I apply it and double-check the boundary case.",
    "I cross-checked this against the mechanism rather than pattern-matching the "
    "phrasing — the surface wording is a bit of a trap.",
    "Quick sanity check on units and a limiting case first; both line up, so I'm "
    "confident in the pick.",
]
SYNTH = [
    "Comparing the candidate answers across the loop, the majority converge and "
    "the judge confirms the response with the strongest justification.",
    "The judge weighed each model's reasoning, discounted the two that hand-waved "
    "the key step, and selected the best-supported answer.",
    "After reconciling the disagreement between the models, one answer is clearly "
    "the most defensible once the shared error is removed.",
]


def hash01(*parts: object) -> float:
    """Deterministic float in [0, 1) from any parts (FNV-1a).

    INVARIANT (spec I1): this is the library's ONLY randomness source — no
    wall-clock, no `random` — so a seed fully determines a run.
    """
    s = ":".join(str(p) for p in parts)
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % 100000) / 100000.0


@dataclass(frozen=True)
class Answer:
    """One model's answer to one question, with its telemetry."""

    choice: str  # canonical key used for voting (an option letter, or the text)
    text: str  # human-readable answer for display
    correct: bool
    reasoning: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost: float  # USD


@runtime_checkable
class EngineBackend(Protocol):
    """The port every answer-producing engine implements."""

    def answer(
        self, model: Model, question: Question, benchmark: BenchmarkSpec, seed: int
    ) -> Answer: ...

    def synth_reasoning(self, seed: int, question: Question) -> str: ...


class SimulatedBackend:
    """Deterministic answer generator — the v0.1 `EngineBackend` adapter.

    Parameters
    ----------
    correlation:
        0 → models err independently (maximum fusion benefit); 1 → models share
        the same difficulty draw (errors are nested, little fusion benefit).
    ability_jitter:
        small per-model accuracy wobble (in accuracy points) so identical-ability
        models still differ a little. Deterministic, seeded.
    """

    def __init__(self, correlation: float = 0.35, ability_jitter: float = 4.0):
        self.correlation = float(correlation)
        self.ability_jitter = float(ability_jitter)

    def accuracy(self, model: Model, benchmark: BenchmarkSpec, seed: int) -> float:
        """Probability in [0.02, 0.98] that `model` answers a `benchmark` item correctly."""
        base = model.ability + benchmark.difficulty_delta
        jitter = (hash01(seed, "ability", model.id, benchmark.id) - 0.5) * 2 * self.ability_jitter
        return _clip((base + jitter) / 100.0, 0.02, 0.98)

    def answer(
        self, model: Model, question: Question, benchmark: BenchmarkSpec, seed: int
    ) -> Answer:
        acc = self.accuracy(model, benchmark, seed)
        # INVARIANT (spec I2): with probability `correlation` the outcome is driven
        # by a SHARED per-question draw, otherwise by the model's own draw. Both
        # draws are uniform and the selector is independent of them, so each
        # model's marginal P(correct) stays exactly `acc` — only the *cross-model*
        # correlation changes.
        shared = hash01(seed, "q", question.id)
        idio = hash01(seed, "m", model.id, question.id)
        use_shared = hash01(seed, "mix", model.id, question.id) < self.correlation
        draw = shared if use_shared else idio
        correct = draw < acc

        choice, text = self._choose(question, model, seed, correct)
        reasoning = REASONING[int(hash01(seed, "r", model.id, question.id) * len(REASONING))]
        tokens_in = max(50, len(question.prompt) // 4)
        tokens_out = 120 + int(hash01(seed, "out", model.id, question.id) * 300)
        latency_ms = 1100 + int(hash01(seed, "ms", model.id, question.id) * 900)
        cost = (tokens_in * model.price_in + tokens_out * model.price_out) / 1_000_000.0
        return Answer(
            choice=choice,
            text=text,
            correct=choice == question.gold_key,
            reasoning=reasoning,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
        )

    def _choose(
        self, question: Question, model: Model, seed: int, correct: bool
    ) -> tuple[str, str]:
        if question.kind == "mcq":
            gold = question.gold_index
            if correct:
                idx = gold
            else:
                wrong = [i for i in range(len(question.options)) if i != gold]
                pick = int(hash01(seed, "w", model.id, question.id) * len(wrong))
                idx = wrong[pick] if wrong else gold
            return LETTERS[idx], f"{LETTERS[idx]}. {question.options[idx]}"
        # free-text
        if correct or not question.distractors:
            choice = question.gold_text
        else:
            d = question.distractors
            choice = d[int(hash01(seed, "w", model.id, question.id) * len(d))]
        return choice, choice

    def synth_reasoning(self, seed: int, question: Question) -> str:
        return SYNTH[int(hash01(seed, "synth", question.id) * len(SYNTH))]


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
