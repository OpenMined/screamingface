"""Construct pinned tiers in the DRACO benchmark family."""

from __future__ import annotations

import hashlib
import json
import textwrap

from url4_cloud.benchmarks._types import Benchmark
from url4_cloud.benchmarks.draco.grading import build_actions
from url4_cloud.benchmarks.draco.prompts import (
    ANSWER_INSTRUCTIONS,
    JUDGE_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
)

JUDGE_MODEL = "openrouter/anthropic/claude-haiku-4-5"

# WHY: DRACO pins its cases in code rather than loading a hub dataset, so provenance
# names the vendoring module and the revision is a content hash of those cases.
CASES_DATASET = "vendored:url4_cloud.benchmarks.draco.cases"

MANIFEST_SCHEMA = "screamingface.benchmark-manifest.v1"


def _cases_revision(cases: tuple[dict[str, object], ...]) -> str:
    # INVARIANT: byte-stable across builds — this revision feeds the leaderboard
    # comparability promise (same manifest id ⇒ same exam), so it must be deterministic.
    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_draco_benchmark(
    *,
    benchmark_id: str,
    version: int,
    title: str,
    cases: tuple[dict[str, object], ...],
    criteria_per_case: int,
    judge_passes: int,
    answer_output_tokens: int,
    synthesis_output_tokens: int,
    judge_output_tokens: int,
    tools: tuple[str, ...],
) -> Benchmark:
    """Build one immutable real-model DRACO tier."""

    answer = textwrap.indent(ANSWER_INSTRUCTIONS, "    ")
    synthesis = textwrap.indent(SYNTHESIS_INSTRUCTIONS, "    ")
    judge = textwrap.indent(JUDGE_INSTRUCTIONS, "    ")
    tool_block = (
        "tools: []" if not tools else "tools:\n" + "\n".join(f"  - {tool}" for tool in tools)
    )
    # INVARIANT: `name` is the stable address (registry key, REST routes, SDK evaluate);
    # `id` is the versioned exam identity — bump `version` whenever cases, instructions,
    # params, tools, or grading change in any score-affecting way. The `-v` separator is
    # deliberate: the id flows into url4 contexts, where `@` is a reserved token.
    manifest = f"""\
schema: {MANIFEST_SCHEMA}
name: {benchmark_id}
id: {benchmark_id}-v{version}
title: {title}
route: /benchmark
cases:
  count: {len(cases)}
provenance:
  cases:
    dataset: {CASES_DATASET}
    revision: sha256:{_cases_revision(cases)}
answer:
  instructions: |
{answer}
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: {answer_output_tokens}
synthesis:
  model: {JUDGE_MODEL}
  instructions: |
{synthesis}
  params:
    reasoning: low
    max_output_tokens: {synthesis_output_tokens}
grader:
  kind: rubric
  criteria_per_case: {criteria_per_case}
  model: {JUDGE_MODEL}
  passes: {judge_passes}
  instructions: |
{judge}
  params:
    reasoning: low
    max_output_tokens: {judge_output_tokens}
aggregator:
  kind: mean
metrics:
  primary: normalized_score
  direction: maximize
{tool_block}
""".encode()
    return Benchmark(
        id=benchmark_id,
        title=title,
        manifest=manifest,
        version=version,
        actions=build_actions(
            # WHY versioned: the aggregate report's `benchmark_id` names the exact exam
            # sat (the leaderboard column key), matching the manifest `id` the SDK checks.
            benchmark_id=f"{benchmark_id}-v{version}",
            judge_passes=judge_passes,
            cases=cases,
        ),
    )


__all__: list[str] = []
