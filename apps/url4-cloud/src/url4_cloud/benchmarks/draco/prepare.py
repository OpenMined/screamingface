"""Build DRACO's declared world — download the dataset, emit artifacts and the `[data]` table.

Run at IMAGE BUILD time, never at run time: a Job's rootfs is read-only apart from `/tmp`, it
holds no HuggingFace credential, and `[data]` routes are exact-match with no wildcard form, so
every artifact must already be declared before the Job starts.

    uv run python -m url4_cloud.benchmarks.draco.prepare --out /opt/benchmarks/draco --limit 5

Emits::

    <out>/cases.json           [{"id": …, "input": …}]  — the ONLY thing a client ever sees
    <out>/criteria/<id>.json   [{id, requirement}]      — WEIGHT-FREE, what the judge reads
    <out>/rubrics/<id>.json    the weighted rubric      — private, read by `aggregate.py`
    <out>/url4.data.toml       the [data] table         — merged into the image's url4.toml

INVARIANT — the judge NEVER sees weights. `grading_mode: "official"` (arXiv:2602.11685 §4.2)
judges one criterion at a time, blind to its weight and to its siblings; a judge that can see a
weight can infer how much a criterion is worth and bias toward the expensive ones. The weights
therefore live ONLY in `rubrics/`, which `aggregate.py` reads after the judging is done.

INVARIANT — `cases.json` carries NO rubric. The whole privacy boundary of the design is that the
client receives case ids and inputs while the rubric stays in the image, so a Candidate cannot be
tuned against the answer key. Adding the rubric column here would silently defeat it.

Dataset: `perplexity-ai/draco` (arXiv:2602.11685). Column mapping mirrors
`screamingface-benchmarks/benchmarks_config/draco.yaml`:

    problem → the research prompt   ·   answer → the weighted rubric JSON   ·   domain → metadata
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DATASET = "perplexity-ai/draco"
COLUMN_QUESTION = "problem"
COLUMN_RUBRIC = "answer"
COLUMN_DOMAIN = "domain"

RETRIEVAL_POLICY_ID = "draco/official"

EXCLUDED_DOMAINS = (
    "huggingface.co/datasets/perplexity-ai/draco",
    "openrouter.ai/blog/announcements/fusion-beats-frontier",
    "paperswithcode.com/dataset/draco",
    # Upstream's entry, kept verbatim so our list stays comparable with the reference harness.
    # It is a MONTH PREFIX (arXiv ids are YYMM.NNNNN), so it blocks all of September 2025.
    "arxiv.org/abs/2509",
    # The DRACO paper ITSELF — "DRACO: a Cross-Domain Benchmark for Deep Research Accuracy,
    # Completeness, and Objectivity", submitted 2026-02-12 (verified against arXiv 2026-07-31).
    # WHY this is a separate entry: the upstream prefix above covers 2025-09 and the paper is
    # 2026-02, so upstream blocks a month that holds nothing and leaves the paper reachable. A
    # candidate reading the benchmark's own paper is the leak this list exists to stop, and it
    # INFLATES the score, so it never looks like a bug.
    "arxiv.org/abs/2602.11685",
)
"""The blocklist a DRACO candidate answers under, copied from
`screamingface-benchmarks/benchmarks_config/draco.yaml`.

DRACO is a deep-research benchmark, so a candidate that retrieves the dataset card, the
reproduction post, or the paper is reading the answer key. That INFLATES the score, which is why
it does not look like a bug.

The SHAPE of these entries is correct: OpenRouter documents wildcards (`*.substack.com`) and
path filtering (`openai.com/blog`) as supported values, and a live probe on 2026-07-31 drove
blocked-host citations to zero on both the `native` and `exa` engines. An earlier note here
claimed path prefixes could not match; that reading came from a probe run while the gateway was
still emitting the WRONG WIRE KEY (`excluded_domains` for `exclude_domains`), so it measured the
typo rather than the value shape. Retracted.

RESOLVED 2026-07-31 — upstream's `arxiv.org/abs/2509` is annotated "DRACO paper preprint range"
but arXiv ids are `YYMM.NNNNN`, so it covers September 2025 while the paper is **2602.11685**,
submitted 2026-02-12 (verified against arXiv). Upstream therefore blocks a month that holds
nothing and leaves the paper itself reachable. Both entries are kept: theirs so the list stays
comparable with the reference harness, ours so the guard actually holds.

AIDEV-NOTE: the benchmarks repo calls the whole list "our best guess" — OpenRouter never
published theirs — so treat it as a floor, not a ceiling. Extend it from the audit logs in eval
JSONLs (`tool_calls` in metadata) as real leak sources turn up. Because the policy is DATA,
each addition is an artifact edit rather than a code release.
"""


class PrepareError(RuntimeError):
    """The dataset could not be turned into a declared world."""


def load_rows(dataset: str = DATASET, limit: int | None = None) -> list[dict[str, Any]]:
    """Download the dataset and return its rows.

    `datasets` is NOT a dependency of url4-cloud. This module runs at image BUILD time on a
    machine that has it; the Job that later serves the artifacts needs only the emitted files.

    # WHY `importlib` rather than a plain import: the same pattern `url4.peer.server` uses for
    # its optional uvicorn extra. A static import would make an optional build-time package look
    # like a hard dependency to every reader and to the type checker, for a module that a
    # deployed Job never imports at all.
    """
    try:
        datasets_mod = importlib.import_module("datasets")
    except ModuleNotFoundError as exc:
        raise PrepareError(
            "the `datasets` package is required to prepare a benchmark — "
            "`uv pip install datasets` in the build environment"
        ) from exc

    loaded = datasets_mod.load_dataset(dataset)
    rows: list[dict[str, Any]] = []
    for split in loaded:  # null split in draco.yaml means "all splits"
        for row in loaded[split]:
            rows.append(dict(row))
            if limit is not None and len(rows) >= limit:
                return rows
    return rows


def parse_rubric(raw: Any, case_id: int) -> dict[str, Any]:
    """Decode the `answer` column into the rubric object the grader walks.

    The column is a JSON STRING holding ``{"sections": [{"criteria": [...]}]}``. A rubric that
    flattens to zero criteria is rejected loudly: it would score every answer 0.0 while looking
    like a successful run.
    """
    rubric = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(rubric, dict) or "sections" not in rubric:
        got = list(rubric)[:5] if isinstance(rubric, dict) else type(rubric).__name__
        raise PrepareError(
            f"case {case_id}: rubric has no 'sections' key — got {got}. A flat criteria list "
            "is a different grader (healthbench_rubric), not this one."
        )
    n_criteria = sum(len(s.get("criteria") or []) for s in rubric["sections"])
    if n_criteria == 0:
        raise PrepareError(f"case {case_id}: rubric flattened to 0 criteria")
    return rubric


def judge_criteria(rubric: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The criteria as the JUDGE sees them — id and requirement, never the weight.

    See the module INVARIANT: `official` grading shows one criterion at a time with no weight,
    so anything extra here is a protocol violation that no test downstream would catch.
    """
    return [
        {"id": criterion.get("id"), "requirement": criterion.get("requirement", "")}
        for section in rubric.get("sections", [])
        for criterion in section.get("criteria") or []
    ]


def build(rows: Sequence[dict[str, Any]], out: Path, route_prefix: str) -> dict[str, Any]:
    """Write `cases.json`, the rubric files, and the generated `[data]` table."""
    rubric_dir = out / "rubrics"
    criteria_dir = out / "criteria"
    rubric_dir.mkdir(parents=True, exist_ok=True)
    criteria_dir.mkdir(parents=True, exist_ok=True)

    cases: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        case_id = index + 1  # 1-based and stable for a given dataset order
        question = row.get(COLUMN_QUESTION)
        if not question:
            raise PrepareError(f"case {case_id}: empty {COLUMN_QUESTION!r} column")
        rubric = parse_rubric(row.get(COLUMN_RUBRIC), case_id)
        (rubric_dir / f"{case_id}.json").write_text(json.dumps(rubric, indent=1), encoding="utf-8")
        (criteria_dir / f"{case_id}.json").write_text(
            json.dumps(judge_criteria(rubric)), encoding="utf-8"
        )
        cases.append(
            {"id": case_id, "input": question, "domain": row.get(COLUMN_DOMAIN) or "unknown"}
        )

    write_policy(out)
    (out / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    (out / "url4.data.toml").write_text(render_data_table(cases, out, route_prefix), "utf-8")
    return {"cases": len(cases), "out": str(out)}


def write_policy(out: Path) -> Path:
    """Emit the retrieval policy an expression names with `;web_search_policy=`.

    An OBJECT rather than a bare array so the policy can version itself — `id` is what a
    published score cites — and can later carry other retrieval settings without a second route.

    INVARIANT: an EMPTY blocklist is rejected HERE, at build time. The runner deliberately
    accepts an empty policy, because a benchmark may declare unrestricted retrieval as an
    explicit, attributable statement — but for DRACO an empty list means the generator broke, and
    a generation bug belongs to the build rather than to a run that would score high and look
    clean.
    """
    if not EXCLUDED_DOMAINS:
        raise PrepareError("the retrieval policy is empty — a DRACO run needs its blocklist")
    policy_dir = out / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    path = policy_dir / "retrieval.json"
    path.write_text(
        json.dumps(
            {
                "id": RETRIEVAL_POLICY_ID,
                "excluded_domains": list(EXCLUDED_DOMAINS),
                "note": (
                    "Best-effort proxy for the OpenRouter post's blocklist, which was never "
                    "published. Entries are UNVERIFIED — see prepare.EXCLUDED_DOMAINS."
                ),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return path


def render_data_table(cases: Sequence[dict[str, Any]], out: Path, route_prefix: str) -> str:
    """Render the `[data]` table — one entry per artifact, because routing is exact-match.

    Rubrics are declared as `file` providers rather than inline values so an operator can edit
    one in a running node without a rebuild, and so the table stays readable at 100+ cases.
    """
    lines = [
        "# GENERATED by url4_cloud.benchmarks.draco.prepare — do not edit by hand.",
        f"# {len(cases)} case(s) from {DATASET}. Regenerate after any dataset change.",
        "#",
        "# Routing is exact-match: there is no wildcard form, so every artifact is declared.",
        "",
        "[data]",
        f'"{route_prefix}/cases" = '
        f'{{ file = "{out}/cases.json", media_type = "application/json" }}',
        # The retrieval policy an expression names with `;web_search_policy=`. Declared like any
        # other artifact: that is what puts the blocklist inside the recipe the scoreboard hashes,
        # instead of in operator config where an unguarded run would hash like an honest one.
        f'"{route_prefix}/policy/retrieval" = '
        f'{{ file = "{out}/policy/retrieval.json", media_type = "application/json" }}',
    ]
    # Only the JUDGE-facing criteria are declared as routes. `rubrics/` is deliberately NOT
    # addressable: it carries the weights, and an expression that could fetch one could feed it
    # to the judge. `aggregate.py` reads it off disk instead.
    lines.extend(
        f'"{route_prefix}/criteria/{case["id"]}" = '
        f'{{ file = "{out}/criteria/{case["id"]}.json", media_type = "application/json" }}'
        for case in cases
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="draco-prepare", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/opt/benchmarks/draco"))
    parser.add_argument("--dataset", default=DATASET)
    parser.add_argument("--limit", type=int, default=None, help="cap the case count (probes)")
    parser.add_argument("--route-prefix", default="/draco", help="url4 path prefix for artifacts")
    args = parser.parse_args(argv)

    try:
        summary = build(load_rows(args.dataset, args.limit), args.out, args.route_prefix)
    except PrepareError as exc:
        print(f"prepare failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
