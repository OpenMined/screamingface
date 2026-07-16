"""Benchmark question loading without leaking gated GPQA examples."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from importlib import import_module
from importlib.resources import files

from screamingface.errors import DatasetUnavailable


@dataclass(frozen=True)
class Question:
    id: str
    subject: str
    text: str
    options: tuple[str, ...]
    answer: int

    def prompt(self) -> str:
        choices = "\n".join(f"{chr(65 + i)}. {value}" for i, value in enumerate(self.options))
        return f"{self.text}\n\n{choices}\n\nReply with only A, B, C, or D."


def load_mock_questions(first: int) -> tuple[Question, ...]:
    if first < 1:
        raise ValueError("first must be positive")
    raw = files("screamingface._data").joinpath("gpqa_shaped_synthetic.json").read_text()
    rows = json.loads(raw)
    if first > len(rows):
        raise ValueError(f"mock sample contains {len(rows)} questions; requested {first}")
    return tuple(
        Question(
            id=row["id"],
            subject=row["subject"],
            text=row["question"],
            options=tuple(row["options"]),
            answer=row["answer"],
        )
        for row in rows[:first]
    )


def load_live_questions(first: int, seed: int) -> tuple[Question, ...]:
    """Load authorized GPQA Diamond rows without persisting or rendering them."""
    if first < 1:
        raise ValueError("first must be positive")
    try:
        load_dataset = import_module("datasets").load_dataset
    except ImportError as exc:
        raise DatasetUnavailable(
            "Live GPQA requires the 'datasets' extra: uv sync --extra datasets"
        ) from exc
    dataset = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")
    if first > len(dataset):
        raise ValueError(f"GPQA Diamond contains {len(dataset)} rows; requested {first}")
    return tuple(_gpqa_question(dataset[index], index, seed) for index in range(first))


def _gpqa_question(row, index: int, seed: int) -> Question:
    correct = str(row["Correct Answer"])
    options = [correct, *(str(row[f"Incorrect Answer {n}"]) for n in range(1, 4))]
    random.Random(f"screamingface-gpqa:{seed}:{index}").shuffle(options)
    return Question(
        id=f"gpqa-diamond-{index}",
        subject="science",
        text=str(row["Question"]),
        options=tuple(options),
        answer=options.index(correct),
    )
