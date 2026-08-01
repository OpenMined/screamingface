"""Benchmark manifests published to the ScreamingFace Client.

The manifest is the one control-plane description of a Runner-native benchmark. It names the
data and reducer routes declared by ``url4.toml`` and carries the pinned prompts and model
settings needed to compile one complete URL4 expression per Candidate. Runtime benchmark
behavior does not live here: cases and criteria are data providers, and scoring is the declared
``/benchmark`` command.

The set is fixed at build time, so constants avoid filesystem I/O and make malformed or drifting
manifests a test-time failure. Every registry key must equal the top-level ``id`` in its value.
"""

from __future__ import annotations

import hashlib
import textwrap

from url4_cloud.benchmarks.draco.prompts import (
    ANSWER_INSTRUCTIONS,
    JUDGE_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
)


def _draco_lite() -> str:
    answer = textwrap.indent(ANSWER_INSTRUCTIONS, "    ")
    synthesis = textwrap.indent(SYNTHESIS_INSTRUCTIONS, "    ")
    judge = textwrap.indent(JUDGE_INSTRUCTIONS, "    ")
    return f"""\
id: draco-lite
title: DRACO Lite
description: Research-quality rubric evaluation.
dataset: perplexity-ai/draco
cases:
  count: 100
  route: /draco/cases
answer:
  instructions: |
{answer}
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
synthesis:
  model: anthropic/claude-haiku-4-5
  instructions: |
{synthesis}
  params:
    reasoning: low
    max_output_tokens: 4096
grader:
  kind: rubric
  criteria_route: /draco/criteria/{{case_id}}
  criteria_per_case: 10
  model: openrouter/google/gemini-3.1-pro-preview
  passes: 3
  instructions: |
{judge}
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
aggregator:
  kind: mean
  route: /benchmark
metrics:
  primary: normalized_score
  direction: maximize
tools:
  - web_search
  - web_fetch
"""


DRACO_LITE = _draco_lite()

MANIFESTS: dict[str, str] = {"draco-lite": DRACO_LITE}
"""Every published manifest, keyed by its own `id`."""

DEFAULT_BENCHMARK_ID = "draco-lite"
"""The benchmark selected when ``sf.evaluate`` omits its benchmark argument."""


def field(text: str, name: str) -> str | None:
    """The value of a TOP-LEVEL ``name: value`` line, or ``None``.

    Deliberately not a YAML parser: the catalog needs three scalars for its summary, and pulling
    in a parser would let a manifest's shape drift into something only a parser can explain. Lines
    that are indented belong to a nested block (`routes:`, `tools:`) and are skipped, so
    ``field(text, "cases")`` cannot accidentally return the `routes.cases` route.
    """
    for line in text.splitlines():
        if not line[:1].strip():  # indented → nested, not a top-level key
            continue
        key, sep, value = line.partition(":")
        if sep and key.strip() == name:
            return value.strip() or None
    return None


def etag_of(text: str) -> str:
    """A STRONG validator over the exact bytes served.

    Strong (no ``W/``) because the response body is this string verbatim — byte-for-byte equality
    is exactly what the validator asserts. Content-derived rather than a version counter, so two
    manifests can never collide and a manifest edit invalidates caches without anyone remembering
    to bump anything.
    """
    return '"' + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32] + '"'


__all__ = ["DEFAULT_BENCHMARK_ID", "MANIFESTS", "etag_of", "field"]
