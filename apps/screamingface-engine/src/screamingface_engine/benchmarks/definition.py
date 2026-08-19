"""Shared definitions and authoring helpers for Engine-owned Benchmarks."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from screamingface_engine.benchmarks.contract import CANDIDATE_BINDING, CANDIDATE_ROUTE
from screamingface_engine.retrieval_policy import normalize_excluded_domains
from url4 import Node, RelExpr, build, expr, render, src, struct, text
from url4.peer.server import Url4Node

CANDIDATE_REF = f"${CANDIDATE_BINDING}"

type BenchmarkInstaller = Callable[[Url4Node, Path], None]
type CheckCost = Literal["free", "paid"]

_BENCHMARK_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _no_routes(_node: Url4Node, _assets_root: Path) -> None:
    """Default installer for a protocol that needs no private routes or assets."""


@dataclass(frozen=True, slots=True)
class CheckSurface:
    """One benchmark's advertised mid-run checking capability (OME-796).

    A loop recipe compiled client-side writes `check_route` into its check
    steps (never a hardcoded path) and budgets by `expected_check_cost`. An
    ABSENT surface means the benchmark cannot check mid-run — the client's
    preflight refuses a loop recipe before any money moves, and for MCQ-style
    benchmarks that refusal is correct behavior, not a gap (pass/fail feedback
    over a handful of options is an elimination attack).
    """

    check_route: str
    feedback_intent: str
    expected_check_cost: CheckCost

    def __post_init__(self) -> None:
        if not isinstance(self.check_route, str) or not self.check_route.startswith("/"):
            raise ValueError("CheckSurface check_route must be an absolute route path")
        if not isinstance(self.feedback_intent, str) or not self.feedback_intent.strip():
            raise ValueError("CheckSurface feedback_intent must be non-empty text")
        if self.expected_check_cost not in {"free", "paid"}:
            raise ValueError("CheckSurface expected_check_cost must be 'free' or 'paid'")

    def as_block(self) -> dict[str, str]:
        return {
            "check_route": self.check_route,
            "feedback_intent": self.feedback_intent,
            "expected_check_cost": self.expected_check_cost,
        }


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Immutable metadata plus one complete URL4 protocol builder.

    ``build`` is pure: it specializes the protocol to an exact selected case count and returns a
    structured URL4 node. ``install`` owns any private routes and validates immutable assets
    against the explicitly injected root before a run can spend money.
    """

    id: str
    title: str
    description: str
    revision: str
    case_count: int
    build: Callable[[int], Node]
    install: BenchmarkInstaller = _no_routes
    check_surface: CheckSurface | None = None

    def __post_init__(self) -> None:
        for name in ("title", "description", "revision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Benchmark {name} must be non-empty text")
        if not isinstance(self.id, str) or _BENCHMARK_ID.fullmatch(self.id) is None:
            raise ValueError("Benchmark id must be one lowercase identifier")
        if (
            isinstance(self.case_count, bool)
            or not isinstance(self.case_count, int)
            or self.case_count < 1
        ):
            raise ValueError("Benchmark case_count must be a positive integer")

    def catalog_entry(self) -> dict[str, object]:
        """Return metadata sufficient for one-request Benchmark discovery."""

        return {
            "object": "benchmark",
            **self._metadata(),
            "href": f"/v1/benchmarks/{self.id}",
        }

    def _metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "revision": self.revision,
            "case_count": self.case_count,
        }
        if self.check_surface is not None:
            metadata["check_surface"] = self.check_surface.as_block()
        return metadata

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
            "candidate_binding": CANDIDATE_BINDING,
            "url4": render(protocol),
        }


def candidate(
    input: str,
    *,
    binding: str = CANDIDATE_REF,
    web_search: bool,
    web_search_exclude: Sequence[str] = (),
    progress_route: str | None = None,
    case_id: str | None = None,
    selected_case_count: int | None = None,
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
    candidate_input, sources = _candidate_progress_input(
        input,
        progress_route=progress_route,
        case_id=case_id,
        selected_case_count=selected_case_count,
    )
    call = RelExpr(
        path=CANDIDATE_ROUTE,
        context=candidate_input,
        intent=text(binding),
        params=tuple(params),
    )
    invocation = src(call, name="candidate_invocation", weight=0.0)
    if progress_route is None:
        # A parameterized relative call needs an expression boundary to round-trip canonically.
        return expr(*sources, invocation, intent=text("$candidate_invocation"))
    assert case_id is not None and selected_case_count is not None
    grading_progress = RelExpr(
        path=progress_route,
        context=render(struct({"case_id": case_id, "value": "$candidate_invocation"})),
        intent=text(f"grading:{selected_case_count}"),
    )
    return expr(
        *sources,
        invocation,
        src(grading_progress, name="grading_progress", weight=0.0),
        intent=text("$grading_progress"),
    )


def _candidate_progress_input(
    input: str,
    *,
    progress_route: str | None,
    case_id: str | None,
    selected_case_count: int | None,
) -> tuple[str, tuple[Node, ...]]:
    values = (progress_route, case_id, selected_case_count)
    if all(value is None for value in values):
        return input, ()
    if not isinstance(progress_route, str) or not progress_route.startswith("/"):
        raise ValueError("progress_route must be an absolute URL4 path")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case_id must be non-empty URL4 text")
    if (
        isinstance(selected_case_count, bool)
        or not isinstance(selected_case_count, int)
        or selected_case_count < 1
    ):
        raise ValueError("selected_case_count must be a positive integer")
    progress = RelExpr(
        path=progress_route,
        context=render(struct({"case_id": case_id, "value": input})),
        intent=text(f"candidate:{selected_case_count}"),
    )
    return "$progress_input", (src(progress, name="progress_input", weight=0.0),)


def link_candidate(candidate_expression: Node | str, protocol: Node | str) -> str:
    """Bind one Candidate expression to a fetched Benchmark protocol, ready to execute.

    This is the executable half of the resource contract `candidate_binding` names: the Candidate
    is carried as an inert text source under that name, which is what makes the protocol's
    `$candidate` resolve. It weighs 0.0 because it contributes no content of its own — the
    protocol decides where and how often the Candidate is invoked.
    """

    return render(
        expr(
            src(
                text(_as_text(candidate_expression)),
                name=CANDIDATE_BINDING,
                weight=0.0,
            ),
            protocol if isinstance(protocol, Node) else build(protocol),
            intent=text(""),
        )
    )


def _as_text(value: Node | str) -> str:
    return value if isinstance(value, str) else render(value)


__all__ = [
    "CANDIDATE_REF",
    "Benchmark",
    "BenchmarkInstaller",
    "CheckSurface",
    "candidate",
    "link_candidate",
]
