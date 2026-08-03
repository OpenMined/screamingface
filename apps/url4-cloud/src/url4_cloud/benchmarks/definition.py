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
class BenchmarkMethod:
    """One named execution protocol of a Benchmark — same exam material, different DAG.

    WHY methods instead of sibling registry entries: two protocols over one exam (e.g.
    IFEval single-pass vs the LANL corrective chain) are NOT two benchmarks — separate
    catalog entries invite cross-column comparisons the protocols forbid. A method keeps
    one catalog identity while every variant keeps its own revision (its own exam hash).
    """

    name: str
    revision: str
    build: Callable[[int], Node]


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Metadata plus ordinary Python that builds one Engine-owned URL4 expression.

    A Benchmark author owns this definition plus its ``build`` and ``install`` functions. The
    public resource, caching, validation, Candidate linkage, asset-root resolution, and execution
    transport remain shared infrastructure.

    ``methods`` is optional: a benchmark with one protocol leaves it empty and nothing
    changes. When present, the top-level ``revision``/``build`` MUST be the default
    method's — the invariants below enforce it.
    """

    id: str
    title: str
    description: str
    revision: str
    case_count: int
    required_models: tuple[str, ...]
    build: Callable[[int], Node]
    install: Callable[[Url4Node, Path], None]
    methods: tuple[BenchmarkMethod, ...] = ()
    default_method: str = ""
    # Optional candidate-facing action routes (e.g. a verifier benchmark's check /
    # select / finalize). Advertised additively in the resource so an SDK recipe can
    # address them without hardcoding revision prefixes.
    actions: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.methods:
            if self.default_method:
                raise ValueError("a Benchmark without methods cannot name a default_method")
            return
        names = [method.name for method in self.methods]
        if len(set(names)) != len(names):
            raise ValueError("Benchmark method names must be unique")
        default = next((m for m in self.methods if m.name == self.default_method), None)
        if default is None:
            raise ValueError("default_method must name one of the Benchmark's methods")
        if default.revision != self.revision:
            raise ValueError("Benchmark revision must equal its default method's revision")

    def method_names(self) -> tuple[str, ...]:
        return tuple(method.name for method in self.methods)

    def resource(self, limit: int | None, method: str | None = None) -> dict[str, object]:
        """Build the exact JSON representation fetched by an SDK."""

        selected_method = self._select_method(method)
        build = selected_method.build if selected_method else self.build
        revision = selected_method.revision if selected_method else self.revision
        selected = self.case_count if limit is None else min(limit, self.case_count)
        if selected < 1:
            raise ValueError("Benchmark case selection must not be empty")
        expression = build(selected)
        if not isinstance(expression, Node):
            raise TypeError("Benchmark build must return a URL4 Node")
        resource: dict[str, object] = {
            "schema": "screamingface.benchmark.v1",
            "id": self.id,
            "revision": revision,
            "case_count": selected,
            "total_case_count": self.case_count,
            "required_models": list(self.required_models),
            "url4": render(expression),
        }
        if selected_method is not None:
            # Additive fields, present only for multi-method benchmarks — a
            # single-protocol manifest stays byte-identical to the pre-method format.
            resource["method"] = selected_method.name
            resource["methods"] = list(self.method_names())
            resource["default_method"] = self.default_method
        if self.actions is not None:
            resource["actions"] = dict(self.actions)
        return resource

    def _select_method(self, method: str | None) -> BenchmarkMethod | None:
        if not self.methods:
            if method is not None:
                raise ValueError(f"Benchmark {self.id!r} has no methods; got {method!r}")
            return None
        selected = method or self.default_method
        for candidate_method in self.methods:
            if candidate_method.name == selected:
                return candidate_method
        raise ValueError(f"unknown method {selected!r} for Benchmark {self.id!r}")


def candidate(input: str, case: str | None = None) -> RelExpr:
    """Invoke the structurally linked Candidate with one Benchmark-owned input.

    ``case`` optionally passes the case identity as a second named context slot —
    the Runner binds it as ``$case`` in the Candidate's lexical scope so candidate-
    side loops can address the benchmark's verifier (OME-727). Case rides FIRST so
    the slot parse is immune to whatever the input text contains.
    """

    if not isinstance(input, str) or not input:
        raise ValueError("Candidate Invocation input must be non-empty URL4 context")
    if case is None:
        context = input
    else:
        if not isinstance(case, str) or not case:
            raise ValueError("Candidate Invocation case must be a non-empty reference")
        context = f"case: {case}, input: {input}"
    return RelExpr(path=CANDIDATE_ROUTE, context=context, intent=Text("$candidate"))


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


__all__ = ["Benchmark", "BenchmarkMethod", "candidate", "chat_input"]
