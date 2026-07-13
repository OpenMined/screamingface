"""Benchmark datasets — real questions, offline-first, deterministic subsampling.

WHY offline-first (a deliberate deviation from the prototype's hub-first order):
the executed quickstart notebook must reproduce on GitHub/Colab with no network
and no HF terms-acceptance, so the bundled sample is the default and the
HuggingFace Hub is opt-in via ``offline=False``. Grading itself always goes
through the `EngineBackend` port; the dataset only supplies the *questions*.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .catalog import BenchmarkSpec, benchmark_spec
from .engine import LETTERS, hash01

_DATA_DIR = os.path.join(os.path.dirname(__file__), "_data")


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    kind: str  # "mcq" | "free"
    options: tuple = ()  # mcq option texts
    gold_index: int = -1  # mcq correct option
    gold_text: str = ""  # free-text canonical answer
    distractors: tuple = ()  # free-text wrong answers
    subject: str = ""

    @property
    def gold_key(self) -> str:
        """The canonical voting key for the correct answer (letter for MCQ)."""
        if self.kind == "mcq":
            return LETTERS[self.gold_index]
        return self.gold_text

    @property
    def gold(self) -> str:
        """Human-readable correct answer."""
        if self.kind == "mcq":
            return f"{LETTERS[self.gold_index]}. {self.options[self.gold_index]}"
        return self.gold_text


@dataclass
class Benchmark:
    spec: BenchmarkSpec
    questions: list[Question]
    source: str = "offline-sample"

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def name(self) -> str:
        return self.spec.name

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self):
        return iter(self.questions)

    def __getitem__(self, i: int) -> Question:
        return self.questions[i]

    def __repr__(self) -> str:
        return f"Benchmark({self.name!r}, {len(self)} questions, source={self.source!r})"


def load_benchmark(key: str, n: int = 20, seed: int = 0, offline: bool = True) -> Benchmark:
    """Load `n` questions from a benchmark by id ('gpqa') or name ('GPQA Diamond').

    Offline (bundled sample) by default; pass ``offline=False`` to pull the real
    set from the HuggingFace Hub (needs network, the `datasets` package, and —
    for GPQA — accepted terms on the Hub).
    """
    spec = benchmark_spec(key)
    if offline:
        questions, source = _load_offline(spec), "offline-sample"
    else:
        questions, source = _load_from_hf(spec)
    return Benchmark(spec=spec, questions=_subsample(questions, n, seed), source=source)


def _subsample(questions: list[Question], n: int, seed: int) -> list[Question]:
    # WHY: rank by a seeded hash of the question id, then restore document order —
    # deterministic per seed (spec I1), stable across processes.
    if n >= len(questions):
        return questions
    order = sorted(range(len(questions)), key=lambda i: hash01(seed, "pick", questions[i].id))
    return [questions[i] for i in sorted(order[:n])]


def _load_offline(spec: BenchmarkSpec) -> list[Question]:
    path = os.path.join(_DATA_DIR, f"{spec.id}.json")
    if not os.path.exists(path):
        raise KeyError(
            f"No bundled sample for benchmark {spec.id!r} yet — v0.1 bundles 'gpqa' only."
        )
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    return [_question(spec, i, row) for i, row in enumerate(rows)]


def _question(spec: BenchmarkSpec, i: int, row: dict) -> Question:
    if row["kind"] == "mcq":
        return Question(
            id=f"{spec.id}::{i}",
            prompt=row["q"],
            kind="mcq",
            options=tuple(row["options"]),
            gold_index=int(row["answer"]),
            subject=row.get("subject", spec.domain.lower()),
        )
    return Question(
        id=f"{spec.id}::{i}",
        prompt=row["q"],
        kind="free",
        gold_text=row["answer"],
        distractors=tuple(row.get("distractors", [])),
        subject=row.get("subject", spec.domain.lower()),
    )


def _load_from_hf(spec: BenchmarkSpec) -> tuple[list[Question], str]:
    # AIDEV-NOTE: v0.1 wires only GPQA; the other benchmarks' loaders land with
    # their notebooks (02_models / 05_leaderboard series work).
    if spec.id != "gpqa":
        raise KeyError(f"HF loading for {spec.id!r} is not wired yet — use offline=True.")
    from datasets import load_dataset  # type: ignore[import-not-found]

    ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")
    out = []
    for i, row in enumerate(ds):
        correct = row["Correct Answer"]
        opts = [
            correct,
            row["Incorrect Answer 1"],
            row["Incorrect Answer 2"],
            row["Incorrect Answer 3"],
        ]
        # deterministic shuffle so the gold answer isn't always option A
        order = sorted(range(4), key=lambda j: hash01("gpqa-shuffle", i, j))
        shuffled = [opts[j] for j in order]
        out.append(
            Question(
                id=f"gpqa::{i}",
                prompt=row["Question"],
                kind="mcq",
                options=tuple(shuffled),
                gold_index=shuffled.index(correct),
                subject=row.get("Subdomain", "science"),
            )
        )
    return out, "huggingface:Idavidrein/gpqa"
