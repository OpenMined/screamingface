"""Current contract example: one benchmark run and one candidate study."""

from __future__ import annotations

import screamingface as sf

RESEARCH_PROMPT = """\
Answer the research question thoroughly. Preserve specific facts and sources, and use
clear prose.
"""

# Uses the SDK's default URL4 engine. Temporarily, that default is the local Docker
# service at http://127.0.0.1:4404. Override it for another deployment:
# sf.config(engine="https://url4.example.org")

researchers = tuple(
    sf.Model(
        model,
        name=name,
        prompt=RESEARCH_PROMPT,
    )
    for name, model in (
        ("codex-researcher", "codex/gpt-5.5"),
        ("gemini-researcher", "gemini/2.5-flash"),
        ("claude-researcher", "claude/sonnet-4.6"),
    )
)

fusion = sf.Fusion(
    "frontier-trio",
    members=researchers,
    reducer=sf.reducers.Model(
        model="codex/gpt-5.5",
        prompt="Synthesize the labeled panel answers into one final answer.",
    ),
)


def quickstart():
    """Load an engine manifest, then execute one complete URL4 benchmark run."""
    benchmark = sf.benchmarks.load("draco@1")
    return benchmark.evaluate(fusion, first=5)


def candidate_study():
    """Compare independently named Recipes over one shared engine-owned case slice."""
    benchmark = sf.benchmarks.load("draco-lite@1")
    return benchmark.evaluate([*researchers, fusion])


def inspect_report(report: sf.Report):
    """Inspect one paired Recipe-versus-member comparison."""
    first_member = report.members["member_1"]
    return {
        "benchmark": report.benchmark_id,
        "recipe": report.recipe_name,
        "url4": report.url4,
        "n_cases": report.n_cases,
        "n_scored": report.n_scored,
        "coverage": report.coverage,
        "score": report.score,
        "baseline": report.baseline,
        "gain": report.gain,
        "recipe_metrics": report.metrics,
        "first_member_model": first_member.model,
        "first_member_score": first_member.score,
        "first_member_metrics": first_member.metrics,
        "failures": report.failures,
        "complete": report.complete,
        "json_compatible": report.to_dict(),
    }


def inspect_study(report: sf.StudyReport):
    """Inspect one ordered candidate comparison without re-running it."""
    best = report.best
    return {
        "benchmark": report.benchmark_id,
        "url4": report.url4,
        "case_ids": report.case_ids,
        "candidate_names": tuple(report.candidates),
        "best": best.name if best is not None else None,
        "complete": report.complete,
        "json_compatible": report.to_dict(),
    }


# Choose one workflow. Running both would create two paid evaluations.
