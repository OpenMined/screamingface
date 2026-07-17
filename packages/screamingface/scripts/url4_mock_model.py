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
    "google/gemini-3.1-pro-preview": 0,
}
_PANEL_ANSWER = re.compile(r"^Panel \d+ \[[^]]+\]:\s*\n\s*([A-D])\s*$", re.MULTILINE)
_PANEL_STRUCT_ANSWER = re.compile(r'["\']?panel_\d+_answer["\']?:\s*["\']([A-D])')
_CRITERION = re.compile(r"<criterion>\s*(.*?)\s*</criterion>", re.DOTALL)
_RESPONSE = re.compile(r"<response>\s*(.*?)\s*</response>", re.DOTALL)
_MOCK_KEYWORD = re.compile(r"\[mock-keyword:\s*([^\]]+)\]", re.IGNORECASE)


def _prompt(row: dict) -> str:
    choices = "\n".join(f"{chr(65 + index)}. {value}" for index, value in enumerate(row["options"]))
    return f"{row['question']}\n\n{choices}\n\nReply with only A, B, C, or D."


def answer(model_id: str, intent: str, context: str = "") -> str:
    try:
        bucket = _BUCKETS[model_id]
    except KeyError as exc:
        raise ValueError(f"unknown mock model {model_id!r}") from exc
    if "<criterion_type>" in context and "<response>" in context:
        return _judge_criterion(context)
    prompt = intent if not context else f"{intent}\n\n{context}"
    result = _fusion_answer(prompt) or _gpqa_answer(prompt, bucket) or _draco_answer(prompt, bucket)
    if result is None:
        raise ValueError("prompt is not part of the deterministic quickstart fixture")
    return result


def _fusion_answer(prompt: str) -> str | None:
    panel_answers = _PANEL_ANSWER.findall(prompt) or _PANEL_STRUCT_ANSWER.findall(prompt)
    if panel_answers:
        counts = Counter(panel_answers)
        highest = max(counts.values())
        return sorted(answer for answer, count in counts.items() if count == highest)[0]
    if "unified" in prompt.lower() and "panel" in prompt.lower():
        found = [keyword for keyword in ("alpha", "beta", "gamma") if keyword in prompt.lower()]
        return "Unified research response: " + ", ".join(found)
    return None


def _gpqa_answer(prompt: str, bucket: int) -> str | None:
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
    return None


def _draco_answer(prompt: str, bucket: int) -> str | None:
    draco_fixture = (
        Path(__file__).parents[1]
        / "src"
        / "screamingface"
        / "_data"
        / "draco_shaped_synthetic.json"
    )
    for row in json.loads(draco_fixture.read_text(encoding="utf-8")):
        if row["problem"] not in prompt:
            continue
        keyword = ("alpha", "beta", "gamma")[bucket]
        return f"Independent research response covering {keyword}."
    return None


def _judge_criterion(prompt: str) -> str:
    criterion_match = _CRITERION.search(prompt)
    response_match = _RESPONSE.search(prompt)
    if criterion_match is None or response_match is None:
        raise ValueError("invalid deterministic DRACO judge prompt")
    keyword_match = _MOCK_KEYWORD.search(criterion_match.group(1))
    if keyword_match is None:
        raise ValueError("deterministic DRACO criterion has no mock keyword")
    keyword = keyword_match.group(1).strip().lower()
    met = keyword in response_match.group(1).lower()
    status = "MET" if met else "UNMET"
    return json.dumps({"explanation": f"keyword {keyword}: {status}", "criterion_status": status})


def main() -> None:
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: url4_mock_model.py MODEL_ID [PROMPT]")
    if len(sys.argv) == 3:
        intent = sys.argv[2]
        context = sys.stdin.read()
    else:
        intent = sys.stdin.read()
        context = ""
    try:
        result = answer(sys.argv[1], intent, context)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    print(result)


if __name__ == "__main__":
    main()
