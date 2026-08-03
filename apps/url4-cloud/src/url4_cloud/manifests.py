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

A manifest describes the BENCHMARK PROTOCOL — what a faithful run requires — not what any one
deployment currently delivers. One field still says more than the stack guarantees, and the gap
is not visible in a result:

* `judge_reasoning: "low"` is pinned by arXiv:2602.11685 §4.2 and is deliberately ABSENT here
  rather than advertised-and-unhonored: `reasoning_effort` has no OpenRouter rule, and the
  gateway fails closed on an unknown parameter.

`tools` names the retrieval a DRACO candidate is meant to have, and as of 2026-08-02 EVERY
answering route delivers it — by one of two mechanisms, per the owner's decision of that date:
provider-side `native_web_search` where OpenRouter supports it, and the runner-driven Tavily loop
(`web_tools`) for `kimi-k2.6`, `deepseek-v4-pro` and `qwen3.6-plus`, which answer `404` to native
search. Both are guarded by the same declared retrieval policy. The judge declares neither, which
is what the paper requires.

AIDEV-NOTE: the two mechanisms are not the same product, and a published comparison should say
so — a native-search candidate and a Tavily candidate did not read the same web. This is a
protocol caveat, not a defect: the alternative on the table (`exa` everywhere, uniform but
different again) was considered and rejected.

AIDEV-NOTE — what holds these honest, and the one thing still open.

1. `routes`, the judge, and the retrieval declarations are pinned against the GENERATOR and
   `url4.toml` by `tests/unit/test_manifest_matches_declared_world.py` — not against a second
   copy of this literal, which would only prove the manifest equals itself.
2. `cases` is the UPSTREAM dataset's size, and a benchmark image now always carries the WHOLE
   dataset — `Dockerfile.benchmark`'s truncating build arg was removed 2026-08-02 precisely
   because a truncated image was indistinguishable from a full one while still advertising 100
   here. Run size is an EXPRESSION concern (`;iteration.slice=0:5`), which leaves this number
   true by construction rather than by anyone remembering.

STILL OPEN: `cases: 100` assumes the upstream dataset has 100 rows. `prepare.load_rows` calls
`load_dataset()` with no `revision=`, so a dataset edit changes the truth of this line with no
signal anywhere. That is the dataset-provenance gap, not a manifest gap — fixing it belongs with
the revision pin.
"""

from __future__ import annotations

import hashlib

DRACO_LITE = """\
id: draco-lite
title: DRACO Lite
description: Research-quality rubric evaluation.
dataset: perplexity-ai/draco
dataset_split: test
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
