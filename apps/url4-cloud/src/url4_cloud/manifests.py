"""Benchmark manifests — the catalog `GET /v1/benchmarks` serves.

A manifest tells a client how to RUN a benchmark: which data routes carry the cases and the
criteria, which judge grades them, and under which protocol. It deliberately says nothing about
where those artifacts live on disk — that is the Runner image's business, and the rubrics behind
`criteria` must stay unreachable from any expression.

WHY constants rather than files: the set is fixed at build time and changes only with a release,
so a file would add I/O, a path to traverse, and a runtime failure mode for no gain. As constants
they are covered by the type checker and by `tests/unit/test_benchmark_manifests.py`, and a
malformed manifest is a build-time error rather than a 500 in front of a caller.

INVARIANT: every entry's registry key equals the `id:` line inside its own text. `MANIFESTS` is
keyed by id, and the route serves the value for that key, so a mismatch would hand a caller a
manifest naming a benchmark they did not ask for.

AIDEV-NOTE: `routes` here must match what the benchmark image's `url4.toml` actually declares
(`prepare.render_data_table`). Nothing enforces that yet — a pinning test in the spirit of
`test_declared_models_match_aigateway.py` is the right home for it once a second benchmark lands.
"""

from __future__ import annotations

import hashlib

DRACO_LITE = """\
id: draco-lite
title: DRACO Lite
description: Research-quality rubric evaluation.
dataset: perplexity-ai/draco
cases: 100
grading: rubric
grading_mode: official
judge: openrouter/google/gemini-3.1-pro-preview
judge_runs: 3
judge_temperature: 0.2
routes:
  cases: /draco/cases
  criteria: /draco/criteria/{case_id}
tools:
  - web_search
  - web_fetch
"""

MANIFESTS: dict[str, str] = {"draco-lite": DRACO_LITE}
"""Every published manifest, keyed by its own `id`."""


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
