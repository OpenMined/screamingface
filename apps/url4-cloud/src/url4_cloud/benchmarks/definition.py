"""Shared definitions and authoring helpers for Engine-owned Benchmarks."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from url4 import Node, RelExpr, Text, expr, render, src, struct
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

    Each definition returns one complete evaluation protocol. Alternative protocols are
    separate Benchmark definitions that may share family assets and runtime functions.
    """

    id: str
    family: str
    variant: str
    title: str
    description: str
    revision: str
    case_count: int
    required_models: tuple[str, ...]
    build: Callable[[int], Node]
    install: Callable[[Url4Node, Path], None]
    # WHY optional: most exams treat the Candidate as one opaque answerer. An exam whose
    # protocol addresses direct Fusion members individually (ifeval-iterative-correction) supplies
    # this second build; the fetch's member count selects it. Absent → member count is
    # ignored and the whole-candidate build serves every shape.
    member_build: Callable[[int, int], Node] | None = None

    def resource(self, limit: int | None, members: int = 0) -> dict[str, object]:
        """Build the exact JSON representation fetched by an SDK."""

        selected = self.case_count if limit is None else min(limit, self.case_count)
        if selected < 1:
            raise ValueError("Benchmark case selection must not be empty")
        if members and self.member_build is not None:
            expression = self.member_build(selected, members)
        else:
            expression = self.build(selected)
        if not isinstance(expression, Node):
            raise TypeError("Benchmark build must return a URL4 Node")
        resource: dict[str, object] = {
            "schema": "screamingface.benchmark.v1",
            "id": self.id,
            "family": self.family,
            "variant": self.variant,
            "revision": self.revision,
            "case_count": selected,
            "total_case_count": self.case_count,
            "required_models": list(self.required_models),
            "url4": render(expression),
        }
        return resource


def candidate(
    input: str,
    *,
    binding: str = "$candidate",
    web_search: bool | None = None,
    web_search_exclude: Sequence[str] = (),
) -> Node:
    """Invoke the structurally linked Candidate with one Benchmark-owned input.

    Retrieval is Benchmark policy, not Candidate policy. These options are carried on the
    ``/candidate`` call and applied to every model call inside the linked Candidate while it is
    evaluated. This keeps the SDK generic, makes the policy visible in the final URL4, and lets
    DRACO require guarded retrieval while IFEval explicitly disables it in the same Runner.
    """

    if not isinstance(input, str) or not input:
        raise ValueError("Candidate Invocation input must be non-empty URL4 context")
    if not isinstance(binding, str) or not binding.startswith("$candidate"):
        raise ValueError("Candidate binding must be a $candidate structural reference")
    params = _candidate_params(web_search, web_search_exclude)
    call = RelExpr(
        path=CANDIDATE_ROUTE,
        context=input,
        intent=Text(binding),
        params=tuple(params),
    )
    if not params:
        return call
    # A parameterized call must be nested to round-trip through URL4's canonical renderer. A
    # bare ``/candidate?...&q=(...)!intent`` currently renders but reparses as an intent-less
    # call; the instrumental group gives the same call an unambiguous expression boundary.
    return expr(
        src(call, name="candidate_result", weight=0.0),
        intent=Text("$candidate_result"),
    )


def _candidate_params(
    web_search: bool | None,
    web_search_exclude: Sequence[str],
) -> tuple[tuple[str, str], ...]:
    excluded = _excluded_domains(web_search_exclude)
    if web_search is False and excluded:
        raise ValueError("web_search_exclude requires web_search to be enabled")
    params: list[tuple[str, str]] = []
    if web_search is not None:
        params.append(("web_search", "true" if web_search else "false"))
    if excluded:
        params.append(("web_search_exclude", ":".join(excluded)))
    return tuple(params)


def _excluded_domains(values: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(values)
    if any(not isinstance(domain, str) or not domain.strip() for domain in selected):
        raise ValueError("web_search_exclude must contain non-empty domains")
    if any(":" in domain or "," in domain for domain in selected):
        raise ValueError("web_search_exclude domains cannot contain ':' or ','")
    return selected


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
