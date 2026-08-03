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
    # INVARIANT: BARE HOSTS ONLY — no paths, no wildcards, no schemes.
    #
    # MEASURED 2026-08-02 (straight to OpenRouter and through the deployed gateway on kind): the
    # provider accepts a host and REJECTS anything longer, with a 400 that kills the whole request:
    #
    #     ["arxiv.org"]                -> 200
    #     ["arxiv.org/abs/2602.11685"] -> 400  "Invalid domain 'arxiv.org/abs/2602.11685'"
    #     ["*.substack.com"]           -> 400
    #
    # This list was page-shaped until that measurement, which means every native answering call in
    # a DRACO run was a hard 400 — a run that finished in five seconds, reported
    # `terminated: succeeded`, and scored nothing. No earlier test caught it: they all used a bare
    # host in a probe policy, and only the real expression carries the real list.
    #
    # OpenRouter's own docs describe wildcards and path filtering as supported values. They are not
    # supported by the provider behind native search, and an earlier note here retracted the
    # "paths do not match" concern on the strength of those docs. Reasoning from documentation is
    # what cost this feature a working guard twice; measure the effect.
    #
    # TRADEOFF, owner decision 2026-08-02: whole SITES are blocked. `arxiv.org` and
    # `huggingface.co` are legitimate deep-research sources, so this makes a candidate look worse
    # at research than it is — a real distortion that belongs beside any published score. It was
    # chosen over under-blocking, which INFLATES scores, and an inflated score is the one nobody
    # audits.
    "arxiv.org",
    "huggingface.co",
    "openrouter.ai",
    "paperswithcode.com",
    # Mirrors that republish the paper under their own hosts, so blocking arxiv.org alone leaves
    # it reachable. Each was observed in a live result set while probing the entries above.
    "alphaxiv.org",
    "semanticscholar.org",
    # The authors' own write-up of the DRACO evaluation — observed citing DRACO material directly
    # in live searches. A subdomain, so `perplexity.ai` at large stays reachable.
    "research.perplexity.ai",
)
"""The blocklist a DRACO candidate answers under, derived from
`screamingface-benchmarks/benchmarks_config/draco.yaml` and reduced to HOSTS.

DRACO is a deep-research benchmark, so a candidate that retrieves the dataset card, the
reproduction post, or the paper is reading the answer key. That INFLATES the score, which is why
it does not look like a bug.

Upstream's list is page-shaped (`huggingface.co/datasets/perplexity-ai/draco`,
`arxiv.org/abs/2509`). Those values cannot ship: the provider rejects anything longer than a host
with a 400 that fails the entire call, so a page-shaped list does not weaken the guard — it stops
the benchmark. Ours is therefore NOT byte-comparable with the reference harness, and that is a
deliberate divergence rather than a drift.

AIDEV-NOTE: still a floor, not a ceiling — the benchmarks repo calls their list "our best guess"
and OpenRouter never published theirs. Extend it from the audit logs in eval JSONLs (`tool_calls`
in metadata) as real leak sources turn up. Because the policy is DATA, each addition is an
artifact edit rather than a code release. Add HOSTS; anything longer is a 400.
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
    # INVARIANT: bare hosts only, enforced at BUILD time. A path or wildcard is a 400 from the
    # provider on every answering call, which surfaces as a run that terminates SUCCEEDED with a
    # zero score — so the build is the last place it can still be loud. MEASURED 2026-08-02:
    # "Invalid domain 'arxiv.org/abs/2602.11685'".
    malformed = sorted(d for d in EXCLUDED_DOMAINS if any(c in d for c in "/*:"))
    if malformed:
        raise PrepareError(
            f"retrieval policy entries must be bare hosts, got {malformed} — a path or wildcard "
            "is rejected by the provider with a 400 that fails every answering call"
        )
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
