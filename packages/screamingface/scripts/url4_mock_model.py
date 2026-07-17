"""Deterministic command backend for the URL4-only quickstart."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_BUCKETS = {
    "codex/gpt-5.5": 0,
    "gemini-cli/gemini-2.5-pro": 1,
    "anthropic/claude-sonnet-4-6": 2,
}
_PANEL_ANSWER = re.compile(r"^Panel \d+ \[[^]]+\]:\s*\n\s*([A-D])\s*$", re.MULTILINE)


def _prompt(row: dict) -> str:
    choices = "\n".join(f"{chr(65 + index)}. {value}" for index, value in enumerate(row["options"]))
    return f"{row['question']}\n\n{choices}\n\nReply with only A, B, C, or D."


def answer(model_id: str, prompt: str) -> str:
    try:
        bucket = _BUCKETS[model_id]
    except KeyError as exc:
        raise ValueError(f"unknown mock model {model_id!r}") from exc
    panel_answers = _PANEL_ANSWER.findall(prompt)
    if panel_answers:
        counts = Counter(panel_answers)
        highest = max(counts.values())
        return sorted(answer for answer, count in counts.items() if count == highest)[0]
    fixture = (
        Path(__file__).parents[1] / "src" / "screamingface" / "_data" / "gpqa_shaped_synthetic.json"
    )
    rows = json.loads(fixture.read_text(encoding="utf-8"))
    for index, row in enumerate(rows):
        if prompt.strip() != _prompt(row).strip():
            continue
        correct = int(row["answer"])
        wrong = index in range(bucket * 4, bucket * 4 + 4)
        choice = (correct + 1) % len(row["options"]) if wrong else correct
        return chr(65 + choice)
    raise ValueError("prompt is not part of the deterministic quickstart fixture")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: url4_mock_model.py MODEL_ID")
    try:
        result = answer(sys.argv[1], sys.stdin.read())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    print(result)


if __name__ == "__main__":
    main()
