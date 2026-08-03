"""IFEval as one Engine-owned Benchmark — two methods over one judge-free exam.

- ``corrective`` (DEFAULT): the bounded 3-attempt retry chain from Skurikhin et al.,
  "Beyond Leaderboards: Tokenomics of Agentic Small Language Model Ensembles"
  (Los Alamos National Laboratory, https://openreview.net/forum?id=XSIYfTm2h7) —
  the verifier's violations feed each retry. 3x candidate calls; scores are NOT
  comparable to published single-pass IFEval numbers.
- ``single_pass``: the IFEval paper's protocol (https://arxiv.org/abs/2311.07911) — one answer per
  prompt, directly comparable to published IFEval scores.

Both methods share the dataset, the vendored verifier, and every runtime asset; each
carries its own revision (its own exam identity).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from url4 import Node, RelExpr, Text, expr, iterate, render, src
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark, BenchmarkMethod, candidate

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
# Candidate-facing actions (OME-727): deterministic helpers a candidate-side verifier
# loop may call. They are NOT exam-defining (they never influence how the exam grades
# the final answer), so they live under the single-pass prefix without a revision bump.
SELECT_ROUTE = f"{ROUTE_PREFIX}/select"
FINALIZE_ROUTE = f"{ROUTE_PREFIX}/finalize"
ACTIONS = {
    "check": CHECK_ROUTE,
    "select": SELECT_ROUTE,
    "finalize": FINALIZE_ROUTE,
}


def _single_pass_build(case_count: int) -> Node:
    # The judge-free shape: per case, the Candidate call is the check call's direct
    # context — one model invocation, then deterministic verification. No inner fan-out.
    checked_call = RelExpr(
        path=CHECK_ROUTE,
        # WHY case rides into the candidate slot: a candidate-side verifier loop
        # (sf.CorrectiveEnsemble) needs $case in scope to address /check; candidates
        # that never reference $case are unaffected (OME-727).
        context=render(candidate("$item.input", case="$item.id")),
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


# --- the corrective method (default) ----------------------------------------------
# Reproduces Skurikhin et al., "Beyond Leaderboards: Tokenomics of Agentic Small
# Language Model Ensembles" (LANL, https://openreview.net/forum?id=XSIYfTm2h7).

MAX_ATTEMPTS = 3
CORRECTIVE_PROTOCOL_REVISION = "corrective-unrolled-3-attempt-v1"
# WHY the single-pass revision is a hash input: the chain grades with the same
# dataset + verifier, so bumping the plain exam's pins must bump this method too —
# coupled by construction, never by manual bookkeeping.
CORRECTIVE_REVISION = hashlib.sha256(
    "\n".join((REVISION, CORRECTIVE_PROTOCOL_REVISION, str(MAX_ATTEMPTS))).encode()
).hexdigest()[:16]
CORRECTIVE_ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{CORRECTIVE_REVISION}"
CORRECTIVE_AGGREGATE_ROUTE = f"{CORRECTIVE_ROUTE_PREFIX}/aggregate"

_RETRY_INSTRUCTION = (
    "The violations listed in the checker verdict are unmet requirements. "
    "Write a new answer that satisfies every requirement of the original request."
)
# INVARIANT: url4 CONTEXT prose ships unescaped — a single quote corrupts the rendered
# expression's re-parse (checks run with raw $refs, siblings drop) and a top-level comma
# splits the context into slots. Proven by DAG repro (edge_probe5, 2026-08-03); the same
# class of bug as the `@` holdings-token lesson. Keep every context string free of both.
if "'" in _RETRY_INSTRUCTION or "," in _RETRY_INSTRUCTION:
    raise RuntimeError("IFEval corrective retry text must not contain quotes or commas")


def _attempt_input(attempt: int) -> str:
    if attempt == 1:
        return "$item.input"
    previous = attempt - 1
    return (
        "$item.input"
        f" | Your previous answer: $prior_{previous}"
        f" | Checker verdict (JSON): $check_{previous}"
        f" | {_RETRY_INSTRUCTION}"
    )


def _corrective_build(case_count: int) -> Node:
    # Per case: prior_N answers (the Candidate), check_N grades it via the shared
    # check route with the attempt riding in the intent. References enforce the
    # order: attempt N's input names $prior_{N-1} and $check_{N-1}.
    attempt_sources = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempt_sources.append(
            # case rides in every candidate slot (same contract as single_pass) so a
            # candidate-side verifier loop binds $case under EITHER method (OME-727).
            src(
                candidate(_attempt_input(attempt), case="$item.id"),
                name=f"prior_{attempt}",
                weight=0.0,
            )
        )
        attempt_sources.append(
            src(
                RelExpr(
                    path=CHECK_ROUTE,
                    context=f"$prior_{attempt}",
                    intent=Text(f"$item.id:{attempt}"),
                ),
                name=f"check_{attempt}",
                weight=0.0,
            )
        )
    chained = expr(
        *attempt_sources,
        intent=Text(
            "attempt records: "
            + " ".join(f"$check_{attempt}" for attempt in range(1, MAX_ATTEMPTS + 1))
        ),
    )
    rows = iterate(
        CASES_ROUTE,
        body=(src(chained, name="checked", weight=1.0),),
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
            RelExpr(path=CORRECTIVE_AGGREGATE_ROUTE, context="$rows", intent=Text("aggregate")),
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
    description=(
        "The 541-prompt instruction-following benchmark (https://arxiv.org/abs/2311.07911) with "
        "deterministic verification. Default method 'corrective' reproduces the "
        "protocol of 'Beyond Leaderboards: Tokenomics of Agentic Small Language "
        "Model Ensembles' (Skurikhin et al., Los Alamos National Laboratory, "
        "https://openreview.net/forum?id=XSIYfTm2h7) — a bounded 3-attempt retry "
        "chain fed by the checker's violations (3x candidate calls; scores are NOT "
        "comparable to published single-pass IFEval numbers). Select method "
        "'single_pass' for the paper-comparable protocol."
    ),
    # The top-level revision/build are the DEFAULT method's (enforced by Benchmark).
    revision=CORRECTIVE_REVISION,
    case_count=CASE_COUNT,
    # INVARIANT: grading is code — the judge-free exam declares no model requirement.
    required_models=(),
    build=_corrective_build,
    install=_install,
    methods=(
        BenchmarkMethod(name="corrective", revision=CORRECTIVE_REVISION, build=_corrective_build),
        BenchmarkMethod(name="single_pass", revision=REVISION, build=_single_pass_build),
    ),
    default_method="corrective",
    actions=ACTIONS,
)

__all__ = ["IFEVAL", "MAX_ATTEMPTS"]
