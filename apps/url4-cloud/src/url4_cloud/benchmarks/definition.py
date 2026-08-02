"""Shared definitions and authoring helpers for Engine-owned Benchmarks."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from url4 import Node, RelExpr, Text, render, struct
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.contract import (
    CANDIDATE_INPUT_SCHEMA,
    CANDIDATE_MESSAGE_ROLES,
    CANDIDATE_ROUTE,
)


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Metadata plus ordinary Python that builds one Engine-owned URL4 expression.

    A Benchmark author owns this definition plus its ``build`` and ``install`` functions. The
    public resource, caching, validation, Candidate linkage, asset-root resolution, and execution
    transport remain shared infrastructure.
    """

    id: str
    title: str
    description: str
    revision: str
    case_count: int
    required_models: tuple[str, ...]
    build: Callable[[int], Node]
    install: Callable[[Url4Node, Path], None]

    def resource(self, limit: int | None) -> dict[str, object]:
        """Build the exact JSON representation fetched by an SDK."""

        selected = self.case_count if limit is None else min(limit, self.case_count)
        if selected < 1:
            raise ValueError("Benchmark case selection must not be empty")
        expression = self.build(selected)
        if not isinstance(expression, Node):
            raise TypeError("Benchmark build must return a URL4 Node")
        return {
            "schema": "screamingface.benchmark.v1",
            "id": self.id,
            "revision": self.revision,
            "case_count": selected,
            "total_case_count": self.case_count,
            "required_models": list(self.required_models),
            "url4": render(expression),
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


__all__ = ["Benchmark", "candidate", "chat_input"]
