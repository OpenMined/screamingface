"""Canonical IFEval as one Engine-owned, deterministic Benchmark."""

from __future__ import annotations

import hashlib
from pathlib import Path

from url4 import Node, RelExpr, Text, expr, iterate, render, src, struct
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA
from url4_cloud.benchmarks.definition import Benchmark, candidate

BENCHMARK_ID = "ifeval"
CASE_COUNT = 541
DATASET = "google/IFEval"
DATASET_REVISION = "966cd89545d6b6acfd7638bc708b98261ca58e84"
# The pip-installable, bug-fixed fork that inspect_evals pins — vendored under ./vendor.
VERIFIER_REPOSITORY = "josejg/instruction_following_eval"
VERIFIER_REVISION = "0c495b2f95155e8b10acb919ae283bfb4d5be6e2"
# v2: case ids ARE the official IFEval keys (join directly to the official dataset),
# and prepare patches the pinned HF snapshot's one known divergence (key 2785's
# prompt) to the official harness text. Both change the emitted assets, so both live
# in the revision hash via this id.
PROTOCOL_REVISION = "ifeval-official-identity-v2"
CANDIDATE_WEB_SEARCH = False

# The verifier code is the grading contract, so changing it changes the Benchmark revision.
REVISION = hashlib.sha256(
    "\n".join(
        (
            DATASET,
            DATASET_REVISION,
            VERIFIER_REPOSITORY,
            VERIFIER_REVISION,
            PROTOCOL_REVISION,
            CANDIDATE_RESULT_SCHEMA,
            f"candidate_web_search={CANDIDATE_WEB_SEARCH}",
        )
    ).encode()
).hexdigest()[:16]

ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
CASES_ROUTE = f"{ROUTE_PREFIX}/cases"
CHECK_ROUTE = f"{ROUTE_PREFIX}/check"
CASE_EVALUATION_ROUTE = f"{ROUTE_PREFIX}/case-evaluation"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"


def _build(case_count: int) -> Node:
    """Build the canonical one-invocation IFEval expression.

    One Candidate answer per case, graded once — the protocol of Zhou et al.
    (arXiv:2311.07911), so scores compare directly to published IFEval results.
    """

    checked_call = RelExpr(
        path=CHECK_ROUTE,
        context=render(candidate("$item.input", web_search=CANDIDATE_WEB_SEARCH)),
        intent=Text("$item.id"),
    )
    checked = expr(
        src(checked_call, name="record", weight=0.0),
        src(
            RelExpr(
                path=CASE_EVALUATION_ROUTE,
                context=render(struct({"attempt_1": "$record"})),
                intent=Text("$item.id"),
            ),
            name="case_evaluation",
            weight=0.0,
        ),
        intent=Text("$case_evaluation"),
    )
    rows = iterate(
        CASES_ROUTE,
        body=(src(checked, name="checked", weight=0.0),),
        intent=Text("$checked"),
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
                context="$rows",
                intent=Text(f"aggregate:{case_count}"),
            ),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )


def install_ifeval(node: Url4Node, assets: Path) -> None:
    """Install the shared IFEval cases, verifier, and variant reducers."""

    # Lazy import keeps the resource-only control plane from loading verifier runtime deps.
    from url4_cloud.benchmarks.ifeval.runtime import install

    install(node, assets / BENCHMARK_ID)


IFEVAL = Benchmark(
    id=BENCHMARK_ID,
    variant="canonical",
    title="IFEval",
    description=(
        "The canonical 541-prompt instruction-following benchmark "
        "(https://arxiv.org/abs/2311.07911), graded by deterministic strict and loose "
        "verification. Each Case invokes the Candidate exactly once. Case ids are the "
        "official IFEval keys; one pinned-dataset row (key 2785) is patched to the "
        "official harness prompt, whose text matches its graded constraints."
    ),
    revision=REVISION,
    case_count=CASE_COUNT,
    build=_build,
    install=install_ifeval,
)

__all__ = ["IFEVAL", "install_ifeval"]
