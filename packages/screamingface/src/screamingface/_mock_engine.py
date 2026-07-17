"""Deterministic in-process URL4 engine used by zero-setup examples and tests.

This is not a shortcut around URL4. Every request is parsed and executed by a
real :class:`url4.Url4Node`; only the registered model-route handlers return
local deterministic fixtures instead of contacting AI Gateway or a provider.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from hashlib import sha256
from importlib.resources import files

from url4 import Request, Url4Node

_ROUTES = {
    "/codex/gpt-5.5": "codex/gpt-5.5",
    "/gemini/2.5": "gemini-cli/gemini-2.5-pro",
    "/claude/sonnet-4.6": "anthropic/claude-sonnet-4-6",
    "/gemini/3.1-pro-preview": "google/gemini-3.1-pro-preview",
}
_BUCKETS = {
    "codex/gpt-5.5": 0,
    "gemini-cli/gemini-2.5-pro": 1,
    "anthropic/claude-sonnet-4-6": 2,
    "google/gemini-3.1-pro-preview": 0,
}
_PANEL_ANSWER = re.compile(r"^Panel \d+ \[[^]]+\]:\s*\n\s*([A-D])\s*$", re.MULTILINE)
_PANEL_STRUCT_ANSWER = re.compile(r'["\']?panel_\d+_answer["\']?:\s*["\']([A-D])')
_CRITERION = re.compile(r"<criterion>\s*(.*?)\s*</criterion>", re.DOTALL)
_CRITERION_TYPE = re.compile(r"<criterion_type>\s*(.*?)\s*</criterion_type>", re.DOTALL)
_RESPONSE = re.compile(r"<response>\s*(.*?)\s*</response>", re.DOTALL)
_MOCK_KEYWORD = re.compile(r"\[mock-keyword:\s*([^\]]+)\]", re.IGNORECASE)
_MULTIPLE_CHOICE = re.compile(r"Reply with only A, B, C, or D\.", re.IGNORECASE)


@dataclass(slots=True)
class MockUrl4Engine:
    """An ``EnginePort`` backed by a real in-process URL4 node."""

    node: Url4Node = field(default_factory=lambda: create_mock_url4_node())
    expressions: list[str] = field(default_factory=list)

    async def evaluate(self, expression: str) -> str:
        self.expressions.append(expression)
        return (await self.node.evaluate(expression)).text


def create_mock_url4_node() -> Url4Node:
    """Build the deterministic node shared by in-process and HTTP examples."""

    node = Url4Node("screamingface-mock")
    node.data("/healthz", "ok")
    for route, model_id in _ROUTES.items():
        node.endpoint(route)(_model_handler(model_id))
    return node


def _model_handler(model_id: str):
    async def handle(request: Request) -> str:
        return mock_model_answer(model_id, request.intent, request.context)

    return handle


def mock_model_answer(model_id: str, intent: str, context: str = "") -> str:
    """Return one deterministic leaf response for a URL4 model route."""

    try:
        bucket = _BUCKETS[model_id]
    except KeyError as exc:
        raise ValueError(f"unknown mock model {model_id!r}") from exc
    if "<criterion_type>" in context and "<response>" in context:
        result = _judge_criterion(model_id, context)
    else:
        prompt = intent if not context else f"{intent}\n\n{context}"
        result = (
            _fusion_answer(prompt) or _gpqa_answer(prompt, bucket) or _draco_answer(prompt, bucket)
        )
        if result is None and _MULTIPLE_CHOICE.search(prompt):
            result = "ABCD"[(_stable_bucket(model_id, prompt) + bucket) % 4]
        if result is None:
            fingerprint = sha256(f"{model_id}\0{prompt}".encode()).hexdigest()[:8]
            result = f"Deterministic mock response from {model_id} [{fingerprint}]."
    return result


def _fusion_answer(prompt: str) -> str | None:
    panel_answers = _PANEL_ANSWER.findall(prompt) or _PANEL_STRUCT_ANSWER.findall(prompt)
    if panel_answers:
        counts = Counter(panel_answers)
        highest = max(counts.values())
        return sorted(answer for answer, count in counts.items() if count == highest)[0]
    if "unified" in prompt.lower() and "panel" in prompt.lower():
        found = [keyword for keyword in ("alpha", "beta", "gamma") if keyword in prompt.lower()]
        if found:
            return "Unified research response: " + ", ".join(found)
    return None


def _gpqa_answer(prompt: str, bucket: int) -> str | None:
    rows = _fixture("gpqa_shaped_synthetic.json")
    for index, row in enumerate(rows):
        if prompt.strip() != _gpqa_prompt(row).strip():
            continue
        correct = int(row["answer"])
        wrong = index in range(bucket * 4, bucket * 4 + 4)
        choice = (correct + 1) % len(row["options"]) if wrong else correct
        return chr(65 + choice)
    return None


def _gpqa_prompt(row: dict) -> str:
    choices = "\n".join(f"{chr(65 + index)}. {value}" for index, value in enumerate(row["options"]))
    return f"{row['question']}\n\n{choices}\n\nReply with only A, B, C, or D."


def _draco_answer(prompt: str, bucket: int) -> str | None:
    for row in _fixture("draco_shaped_synthetic.json"):
        if row["problem"] in prompt:
            keyword = ("alpha", "beta", "gamma")[bucket]
            return f"Independent research response covering {keyword}."
    return None


def _judge_criterion(model_id: str, prompt: str) -> str:
    criterion_match = _CRITERION.search(prompt)
    response_match = _RESPONSE.search(prompt)
    type_match = _CRITERION_TYPE.search(prompt)
    if criterion_match is None or response_match is None or type_match is None:
        raise ValueError("invalid deterministic DRACO judge prompt")
    keyword_match = _MOCK_KEYWORD.search(criterion_match.group(1))
    if keyword_match is not None:
        keyword = keyword_match.group(1).strip().lower()
        met = keyword in response_match.group(1).lower()
        explanation = f"keyword {keyword}: {'MET' if met else 'UNMET'}"
    else:
        desirable_rate = 70 if type_match.group(1).strip().lower() == "positive" else 30
        met = _stable_bucket(model_id, prompt) < desirable_rate
        explanation = "deterministic mock rubric verdict"
    status = "MET" if met else "UNMET"
    return json.dumps({"explanation": explanation, "criterion_status": status})


def _stable_bucket(model_id: str, prompt: str) -> int:
    digest = sha256(f"{model_id}\0{prompt}".encode()).digest()
    return int.from_bytes(digest[:4]) % 100


@cache
def _fixture(name: str) -> tuple[dict, ...]:
    document = files("screamingface._data").joinpath(name).read_text(encoding="utf-8")
    rows = json.loads(document)
    if not isinstance(rows, list):  # pragma: no cover - package fixture invariant
        raise ValueError(f"mock fixture {name!r} must contain a list")
    return tuple(rows)
