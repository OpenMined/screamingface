"""Shared definitions and authoring helpers for Engine-owned Benchmarks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from url4 import Node, RelExpr, expr, render, src, struct, text
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.contract import (
    CANDIDATE_INPUT_SCHEMA,
    CANDIDATE_MESSAGE_ROLES,
    CANDIDATE_ROUTE,
)
from url4_cloud.retrieval_policy import normalize_excluded_domains

type BenchmarkInstaller = Callable[[Url4Node, Path], None]

_BENCHMARK_ID = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_VARIANT = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _no_routes(
    _node: Url4Node,
    _assets_root: Path,
) -> None:
    """Default installer for a protocol that needs no private routes or assets."""


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Immutable metadata plus one complete URL4 protocol builder.

    ``build`` is pure: it specializes the protocol to an exact selected case count and returns a
    structured URL4 node. ``install`` owns any private routes and validates immutable assets
    against the explicitly injected root before a run can spend money.
    """

    id: str
    variant: str
    title: str
    description: str
    revision: str
    case_count: int
    build: Callable[[int], Node]
    install: BenchmarkInstaller = _no_routes
    case_ids: tuple[int, ...] | None = None
    runtime: str | None = None

    def __post_init__(self) -> None:
        _validate_metadata(self)
        _validate_case_ids(self.case_ids, self.case_count)
        if self.runtime is not None and _VARIANT.fullmatch(self.runtime) is None:
            raise ValueError("Benchmark runtime must be one lowercase path segment")

    def catalog_entry(self) -> dict[str, object]:
        """Return metadata sufficient for one-request Benchmark discovery."""

        return {
            "object": "benchmark",
            **self._metadata(),
            "href": f"/v1/benchmarks/{self.id}",
        }

    def _metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "variant": self.variant,
            "title": self.title,
            "description": self.description,
            "revision": self.revision,
            "case_count": self.case_count,
        }

    def protocol(self, selected_case_count: int) -> Node:
        """Build and type-check one exact selection without rendering it prematurely."""

        if (
            isinstance(selected_case_count, bool)
            or not isinstance(selected_case_count, int)
            or selected_case_count < 1
            or selected_case_count > self.case_count
        ):
            raise ValueError(
                f"Benchmark limit must be between 1 and {self.case_count}, "
                f"got {selected_case_count!r}"
            )
        protocol = self.build(selected_case_count)
        if not isinstance(protocol, Node):
            raise TypeError("Benchmark build must return a URL4 Node")
        return protocol

    def resource(self, limit: int | None = None) -> dict[str, object]:
        """Build one flat, independently executable public resource."""

        selected = self.case_count if limit is None else limit
        protocol = self.protocol(selected)
        return {
            "schema": "screamingface.benchmark.v1",
            **self._metadata(),
            "selected_case_count": selected,
            "url4": render(protocol),
        }


def _validate_metadata(benchmark: Benchmark) -> None:
    for name in ("title", "description", "revision"):
        value = getattr(benchmark, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Benchmark {name} must be non-empty text")
    if not isinstance(benchmark.id, str) or _BENCHMARK_ID.fullmatch(benchmark.id) is None:
        raise ValueError("Benchmark id must contain lowercase slash-qualified path segments")
    if not isinstance(benchmark.variant, str) or _VARIANT.fullmatch(benchmark.variant) is None:
        raise ValueError("Benchmark variant must be one lowercase path segment")
    if (
        isinstance(benchmark.case_count, bool)
        or not isinstance(benchmark.case_count, int)
        or benchmark.case_count < 1
    ):
        raise ValueError("Benchmark case_count must be a positive integer")


def _validate_case_ids(case_ids: tuple[int, ...] | None, case_count: int) -> None:
    if case_ids is None:
        return
    if len(case_ids) != case_count:
        raise ValueError("Benchmark case_ids must match case_count")
    if any(not _is_positive_case_id(case_id) for case_id in case_ids):
        raise ValueError("Benchmark case_ids must be positive integers")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Benchmark case_ids must be unique")


def _is_positive_case_id(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def candidate(
    input: str,
    *,
    binding: str = "$candidate",
    web_search: bool,
    web_search_exclude: Sequence[str] = (),
) -> Node:
    """Invoke a structurally linked Candidate under explicit Benchmark retrieval policy."""

    if not isinstance(input, str) or not input:
        raise ValueError("Candidate Invocation input must be non-empty URL4 context")
    if not isinstance(binding, str) or not binding.startswith("$"):
        raise ValueError("Candidate binding must be a URL4 structural reference")
    if not isinstance(web_search, bool):
        raise TypeError("web_search must be a boolean")
    excluded = normalize_excluded_domains(web_search_exclude)
    if not web_search and excluded:
        raise ValueError("web_search_exclude requires web_search=true")

    params: list[tuple[str, str]] = [("web_search", "true" if web_search else "false")]
    if excluded:
        params.append(("web_search_exclude", ":".join(excluded)))
    call = RelExpr(
        path=CANDIDATE_ROUTE,
        context=input,
        intent=text(binding),
        params=tuple(params),
    )
    # A parameterized relative call needs an expression boundary to round-trip canonically.
    return expr(
        src(call, name="candidate_invocation", weight=0.0),
        intent=text("$candidate_invocation"),
    )


def chat_input(messages: str | Sequence[Mapping[str, object]]) -> str:
    """Carry native chat messages through URL4's string context boundary."""

    selected = messages if isinstance(messages, str) else _chat_json(messages)
    if not selected.strip():
        raise ValueError("Candidate chat messages must be non-empty JSON or a URL4 reference")
    return render(struct({"schema": CANDIDATE_INPUT_SCHEMA, "messages": selected}))


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


__all__ = ["Benchmark", "BenchmarkInstaller", "candidate", "chat_input"]
