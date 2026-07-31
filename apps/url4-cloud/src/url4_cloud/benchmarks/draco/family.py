"""Construct pinned tiers in the DRACO benchmark family."""

from __future__ import annotations

import textwrap

from url4_cloud.benchmarks._types import Benchmark
from url4_cloud.benchmarks.draco.grading import build_actions
from url4_cloud.benchmarks.draco.prompts import (
    ANSWER_INSTRUCTIONS,
    JUDGE_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
)

JUDGE_MODEL = "anthropic/claude-haiku-4-5"


def build_draco_benchmark(
    *,
    benchmark_id: str,
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
    manifest = f"""\
name: {benchmark_id}
id: {benchmark_id}
title: {title}
route: /benchmark
cases:
  count: {len(cases)}
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
        actions=build_actions(
            benchmark_id=benchmark_id,
            judge_passes=judge_passes,
            cases=cases,
        ),
    )


__all__: list[str] = []
