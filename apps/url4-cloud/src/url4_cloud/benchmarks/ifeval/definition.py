"""IFEval as one Engine-owned Benchmark definition — judge-free by construction."""

from __future__ import annotations

import hashlib
from pathlib import Path

from url4 import Node, RelExpr, Text, expr, iterate, render, src
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark, candidate

BENCHMARK_ID = "ifeval"
CASE_COUNT = 541
DATASET = "google/IFEval"
DATASET_REVISION = "966cd89545d6b6acfd7638bc708b98261ca58e84"
# The pip-installable, bug-fixed fork that inspect_evals pins — vendored under ./vendor.
VERIFIER_REPOSITORY = "josejg/instruction_following_eval"
VERIFIER_REVISION = "0c495b2f95155e8b10acb919ae283bfb4d5be6e2"
PROTOCOL_REVISION = "official-strict-loose-v1"
# WHY the verifier is a hash input: IFEval has no judge prompt — the vendored checker code
# IS the grading contract, exactly as JUDGE_INSTRUCTIONS is for draco. Changing the
# verifier changes every published score, so it must change the exam's revision.
REVISION = hashlib.sha256(
    "\n".join(
        (
            DATASET,
            DATASET_REVISION,
            VERIFIER_REPOSITORY,
            VERIFIER_REVISION,
            PROTOCOL_REVISION,
        )
    ).encode()
).hexdigest()[:16]
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
CASES_ROUTE = f"{ROUTE_PREFIX}/cases"
CHECK_ROUTE = f"{ROUTE_PREFIX}/check"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"


def _build(case_count: int) -> Node:
    # The judge-free shape: per case, the Candidate call is the check call's direct
    # context — one model invocation, then deterministic verification. No inner fan-out.
    checked_call = RelExpr(
        path=CHECK_ROUTE,
        context=render(candidate("$item.input")),
        intent=Text("$item.id"),
    )
    # WHY the expr wrap: a bare RelExpr src in an iterate body does not resolve `$item`
    # references — the reference-intent passthrough is what scopes them per item (the
    # same shape draco uses for its per-case criterion_results).
    checked = expr(
        src(checked_call, name="record", weight=0.0),
        intent=Text("$record"),
    )
    rows = iterate(
        CASES_ROUTE,
        body=(src(checked, name="checked", weight=1.0),),
        intent=Text("case"),
        slice=None if case_count == CASE_COUNT else (0, case_count),
        on_error="collect",
    )
    row_set = expr(
        src(rows, name="selected_rows", weight=0.0),
        intent=Text("$selected_rows"),
    )
    return expr(
        src(row_set, name="rows", weight=0.0),
        src(
            RelExpr(
                path=AGGREGATE_ROUTE,
                # The complete row collection stays in context — the wide channel that an
                # in-process handler receives directly, immune to argv size limits.
                context="$rows",
                intent=Text("aggregate"),
            ),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )


def _install(node: Url4Node, assets: Path) -> None:
    # Lazy import keeps the resource-only control-plane path from loading filesystem
    # runtime code (and the vendored verifier's nltk/langdetect imports).
    from url4_cloud.benchmarks.ifeval.runtime import install

    install(node, assets)


IFEVAL = Benchmark(
    id=BENCHMARK_ID,
    title="IFEval",
    description="The 541-prompt instruction-following benchmark with deterministic verification.",
    revision=REVISION,
    case_count=CASE_COUNT,
    # INVARIANT: grading is code — the judge-free exam declares no model requirement.
    required_models=(),
    build=_build,
    install=_install,
)

__all__ = ["IFEVAL"]
