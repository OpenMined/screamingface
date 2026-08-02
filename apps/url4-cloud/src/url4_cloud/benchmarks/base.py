"""Small authoring boundary for Engine-owned Benchmarks."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from url4 import Node, RelExpr, Text, render, struct
from url4_cloud.benchmarks.contract import (
    CANDIDATE_INPUT_SCHEMA,
    CANDIDATE_MESSAGE_ROLES,
    CANDIDATE_ROUTE,
)

type ScoreDirection = Literal["maximize", "minimize"]


@dataclass(frozen=True, slots=True)
class BenchmarkExpression:
    """One selected Benchmark expression and its no-spend inspection facts."""

    node: Node
    candidate_invocations: int


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Metadata plus ordinary Python that builds one Engine-owned URL4 expression.

    A Benchmark author owns only this object and its ``build`` function. The public resource,
    caching, validation, Candidate linkage, and execution transport remain shared infrastructure.
    """

    id: str
    title: str
    description: str
    case_count: int
    primary_metric: str
    score_direction: ScoreDirection
    required_models: tuple[str, ...]
    candidate_capabilities: tuple[str, ...]
    runtime_capabilities: tuple[str, ...]
    build: Callable[[int], BenchmarkExpression]

    def resource(self, limit: int | None) -> dict[str, object]:
        """Build the exact JSON representation fetched by an SDK."""

        selected = self.case_count if limit is None else min(limit, self.case_count)
        expression = self.build(selected)
        _validate_expression(expression, selected)
        return {
            "schema": "screamingface.benchmark.v1",
            "object": "benchmark",
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "case_count": selected,
            "total_case_count": self.case_count,
            "metrics": {
                "primary": self.primary_metric,
                "direction": self.score_direction,
            },
            "capabilities": {
                "candidate": list(self.candidate_capabilities),
                "runtime": list(self.runtime_capabilities),
            },
            "required_models": list(self.required_models),
            "candidate_invocations": expression.candidate_invocations,
            "url4": render(expression.node),
        }


def candidate(input: str) -> RelExpr:
    """Invoke the structurally linked Candidate with one Benchmark-owned input."""

    if not isinstance(input, str) or not input:
        raise ValueError("Candidate Invocation input must be non-empty URL4 context")
    return RelExpr(path=CANDIDATE_ROUTE, context=input, intent=Text("$candidate"))


def chat_input(messages: str | Sequence[Mapping[str, object]]) -> str:
    """Carry native chat messages through URL4's string context boundary.

    Pass ordinary Python message mappings when they are known while authoring. A string may carry
    literal JSON or a URL4 reference whose resolved value is JSON. The versioned envelope lets the
    Runner distinguish native turns from an ordinary text question.
    """

    selected = messages if isinstance(messages, str) else _chat_json(messages)
    if not selected.strip():
        raise ValueError("Candidate chat messages must be non-empty JSON or a URL4 reference")
    return render(
        struct(
            {
                "schema": CANDIDATE_INPUT_SCHEMA,
                "messages": selected,
            }
        )
    )


def _chat_json(messages: object) -> str:
    if isinstance(messages, bytes) or not isinstance(messages, Sequence):
        raise TypeError("Candidate chat messages must be a sequence of mappings or a string")
    if not messages:
        raise ValueError("Candidate chat messages must not be empty")
    selected: list[dict[str, str]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
            raise TypeError(f"Candidate chat message {index} must contain role and content")
        role = message["role"]
        content = message["content"]
        if not isinstance(role, str) or role not in CANDIDATE_MESSAGE_ROLES:
            raise ValueError(f"Candidate chat message {index} has unsupported role {role!r}")
        if not isinstance(content, str):
            raise TypeError(f"Candidate chat message {index} content must be text")
        selected.append({"role": role, "content": content})
    return json.dumps(selected, ensure_ascii=False, separators=(",", ":"))


def _validate_expression(expression: BenchmarkExpression, case_count: int) -> None:
    if not isinstance(expression, BenchmarkExpression):
        raise TypeError("Benchmark build must return a BenchmarkExpression")
    if expression.candidate_invocations < 1:
        raise ValueError("Benchmark must invoke its Candidate at least once")
    if case_count < 1:
        raise ValueError("Benchmark case selection must not be empty")


__all__ = ["Benchmark", "BenchmarkExpression", "candidate", "chat_input"]
