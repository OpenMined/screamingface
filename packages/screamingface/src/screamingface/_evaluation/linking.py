"""Structurally link one Candidate expression into one Benchmark expression."""

from __future__ import annotations

from url4 import Iteration, build, expr, render, src, text


def link_candidate(candidate_url4: str, benchmark_url4: str) -> str:
    """Return one complete URL4 without text substitution or benchmark knowledge."""

    candidate = build(candidate_url4)
    benchmark = build(benchmark_url4)
    if isinstance(benchmark, Iteration):
        # The surface grammar greedily reads a top-level ``*(...)`` as a reduce envelope. This
        # ordinary instrumental passthrough gives the iteration an unambiguous nested boundary.
        benchmark = expr(
            src(benchmark, name="benchmark_result", weight=0.0),
            intent=text("$benchmark_result"),
        )
    linked = expr(
        src(text(render(candidate)), name="candidate", weight=0.0),
        benchmark,
        intent=text(""),
    )
    return render(linked)


__all__: list[str] = []
