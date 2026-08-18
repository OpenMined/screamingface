"""HealthBench worst-30% as Engine-owned Benchmark definitions.

FEATURE: the entry challenge — open-source Fusions try to beat our open-fusion baseline
on the 157 hardest HealthBench Professional rows. Protocol authority is OpenAI
simple-evals ``healthbench_eval.py`` (per-rubric-item LLM judging); scoring is the
challenge metric (UNCLIPPED mean), deliberately not the official clipped HealthBench
score — every description below says so.

References:
    - simple-evals (protocol authority): https://github.com/openai/simple-evals
    - Dataset: https://huggingface.co/datasets/openai/healthbench
    - Paper: https://arxiv.org/abs/2505.08775 (HealthBench, Arora et al., 2025)
"""

from __future__ import annotations

import hashlib

from screamingface_engine.benchmarks.contract import CANDIDATE_RESULT_SCHEMA
from screamingface_engine.benchmarks.definition import Benchmark, CheckSurface, candidate
from screamingface_engine.benchmarks.healthbench import verdict
from screamingface_engine.benchmarks.healthbench.prompts import GRADER_TEMPLATE
from screamingface_engine.benchmarks.healthbench.subset import WORST30_CASE_IDS, subset_sha
from screamingface_engine.benchmarks.protocol import (
    EVALUATION_PROTOCOL_REVISION,
    build_evaluation_protocol,
    preserve_candidate_outcome,
)
from url4 import Node, RelExpr, Text, expr, iterate, render, src, struct

BENCHMARK_ID = "healthbench-worst30"
CASE_COUNT = len(WORST30_CASE_IDS)
DATASET = "openai/healthbench-professional"
DATASET_REVISION = "349962fd46dd02343a0d8a606491baf59154ea1a"
PROTOCOL_REVISION = "worst30-per-item-v2"  # v2: aggregate intent carries the selected count
# WHY: prepare.py's output participates in the answer key; bump this when the preparer's
# emission rules change so a rebuilt image can never serve old routes a different key.
PREPARER_REVISION = "hf-rows-v1"
SCORING = "unclipped-mean-v1"
# WHY: the official professional judge is ResponsesSampler(model="gpt-5.4-2026-03-05",
# reasoning_effort="low") — an OpenAI-internal snapshot pin we cannot reach; OpenRouter
# routes the floating slug. A silent snapshot bump can shift judge behavior between
# runs — a named deviation, mitigated by the Engine-rerun target (OME-762).
JUDGE_MODEL = "openrouter/openai/gpt-5.4"
# WHY: NO temperature pin — the official judge's reasoning branch sends ONLY
# reasoning={"effort":"low"} (not expressible through the gateway yet; named deviation),
# never temperature or an output cap. Provider-default temperature is LOAD-BEARING:
# ``;retry=`` re-sends identical bytes, so only a fresh sample can turn a malformed
# reply into a parseable one (the reference retries forever on fresh samples; the July
# port pinned temp 0 and needed a byte-salt url4 cannot express).
JUDGE_PARAMS = (
    # INVARIANT: Grading is retrieval-free even though the same route serves Candidates.
    ("web_search", "false"),
    # Engine-side safety bound only (DRACO precedent) — the official judge sends none.
    ("max_tokens", "4096"),
)
JUDGE_RETRIES = 2
REVISION = hashlib.sha256(
    "\n".join(
        (
            DATASET,
            DATASET_REVISION,
            PROTOCOL_REVISION,
            EVALUATION_PROTOCOL_REVISION,
            CANDIDATE_RESULT_SCHEMA,
            PREPARER_REVISION,
            subset_sha(),
            JUDGE_MODEL,
            repr(JUDGE_PARAMS),
            str(JUDGE_RETRIES),
            GRADER_TEMPLATE,
            SCORING,
        )
    ).encode()
).hexdigest()[:16]
# The pass criterion of the mid-run check surface (OME-830). Declared here rather than
# in check_policy, which reads this module for the judge pinning.
CHECK_CRITERION = "healthbench-pass.v1"
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
CASES_ROUTE = f"{ROUTE_PREFIX}/cases"
TASKS_ROUTE = f"{ROUTE_PREFIX}/rubric-tasks"
VERDICT_ROUTE = f"{ROUTE_PREFIX}/rubric-verdict"
RUBRIC_EVALUATION_ROUTE = f"{ROUTE_PREFIX}/rubric-evaluation"
CASE_EVALUATION_ROUTE = f"{ROUTE_PREFIX}/case-evaluation"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"
CHECK_SURFACE_ROUTE = f"{ROUTE_PREFIX}/check-surface/{CHECK_CRITERION}"


def _build(case_count: int) -> Node:
    candidate_invocation = candidate("$item.input", web_search=False)
    """Build the whole benchmark as one url4 expression tree (a recipe, not a run).

    Think of it as an exam pipeline, written inside-out because each stage is
    nested in the next. Reading outside-in, the Engine will:

    1. Fetch the Cases (patient conversations) from ``cases_route``, and for each:
    2. Ask the Candidate model to answer the conversation, then fetch that Case's
       rubric items ("did the answer mention X?") from ``tasks_route`` — one judge
       task per rubric item, each carrying the Candidate's answer pre-rendered
       into a grader prompt.
    3. For each rubric item, send the grader prompt to the judge model as a single
       user message (empty intent = no system row, matching the official judge),
       and parse its yes/no verdict via ``verdict_route``. A malformed reply
       raises, so ``;retry=`` re-resolves the NESTED judge call — a fresh sample
       per attempt. That is why the judge call sits inside the verdict expression:
       as a sibling, a malformed-but-successful model call would never be retried.
    4. Roll verdicts up: rubric rows → ``rubric_evaluation_route`` → per-Case score
       at ``case_evaluation_route`` → all Case rows into ``aggregate_route``, which
       computes the challenge metric (unclipped mean). Rows travel as context, not
       argv, so no OS argument-length limit can truncate them.

    ``case_count`` < ``CASE_COUNT`` slices to a partial run (the SDK's ``limit=N``);
    equality means the full set. Every route is revision-pinned.

    Returns the unresolved DAG — the Engine executes it at submission time.
    """
    # Stage 3a — the judge call: send one pre-rendered grader prompt to the judge model.
    # One judge pass per rubric item — the reference grades each item exactly once.
    # INVARIANT: the judge call's intent is EMPTY (`!''`). The Runner maps a non-empty
    # intent to a SYSTEM message, and the official professional judge sends no system
    # row — the entire pre-rendered GRADER_TEMPLATE is its one user message.
    judge_reply = RelExpr(
        path=_model_route(JUDGE_MODEL),
        context="$item.grader_prompt",
        intent=Text(""),
        params=JUDGE_PARAMS,
    )
    # Stage 3b — one graded rubric item: judge reply → parsed verdict → stored row.
    rubric_evaluation = expr(
        # Carry the raw Case and rubric records along (weight 0.0 = data, not scored).
        src("$item.case_record", name="case_record", weight=0.0),
        src("$item.rubric_record", name="rubric_record", weight=0.0),
        # WHY nested, not siblings: the verdict route RAISES a transient error on a
        # malformed reply, and its `;retry=` re-resolves the nested judge call — a
        # fresh sample per attempt (verdict.call docstring). Sibling wiring would
        # retry nothing: a malformed reply is a successful model call.
        verdict.call(
            judge_reply,
            case_id="$item.case_id",
            rubric_id="$item.rubric_id",
            route=VERDICT_ROUTE,
            retry=JUDGE_RETRIES,
        ),
        # Post {case, rubric, verdict} to the rubric-evaluation route → one scored row.
        src(
            RelExpr(
                path=RUBRIC_EVALUATION_ROUTE,
                context=render(
                    struct(
                        {
                            "case": "$case_record",
                            "rubric": "$rubric_record",
                            "evidence": "$verdict",
                        }
                    )
                ),
                intent=Text("$item.case_id"),
            ),
            name="rubric_evaluation",
            weight=0.0,
        ),
        intent=Text("$rubric_evaluation"),
    )
    # Stage 2 — per Case: call the Candidate once, fan out one judge task per rubric item.
    rubric_items = iterate(
        RelExpr(
            path=TASKS_ROUTE,
            # This collection boundary invokes the Candidate exactly once per Case,
            # then fans out one pre-rendered judge task per rubric item.
            context="$candidate_invocation",
            intent=Text("$item.case_id"),
        ),
        body=(src(rubric_evaluation, name="evaluated", weight=0.0),),
        intent=Text("$evaluated"),
    )
    # Stage 4a — roll a Case's rubric rows up into one per-Case score.
    case_evaluation = expr(
        src(rubric_items, name="rubric_rows", weight=0.0),
        src(
            RelExpr(
                path=CASE_EVALUATION_ROUTE,
                context="$rubric_rows",
                intent=Text("$item.case_id"),
            ),
            name="case_evaluation",
            weight=0.0,
        ),
        intent=Text("$case_evaluation"),
    )
    return build_evaluation_protocol(
        cases_route=CASES_ROUTE,
        case_evaluation=preserve_candidate_outcome(
            candidate_invocation=candidate_invocation,
            grading=case_evaluation,
            case_id="$item.id",
        ),
        selected_case_count=case_count,
        available_case_count=CASE_COUNT,
        aggregate_route=AGGREGATE_ROUTE,
    )


def _install(node, assets) -> None:  # type: ignore[no-untyped-def]
    # Lazy import keeps the resource-only control-plane path from loading filesystem
    # runtime code (draco precedent).
    from screamingface_engine.benchmarks.healthbench.runtime import install

    install(node, assets / "healthbench")


HEALTHBENCH_WORST30 = Benchmark(
    id=BENCHMARK_ID,
    title="HealthBench Worst-30% Challenge",
    description=(
        "The 157 hardest conversations from HealthBench Professional — the 30% that "
        "top models score worst on. An AI judge grades each answer against a "
        "physician-written rubric; safety mistakes subtract points, so per-case scores "
        "can be negative. Challenge score = plain average of the 157 case scores, "
        "negatives kept (the official HealthBench score floors negative averages at 0, "
        "which would flatten this hard subset to all-zeros)."
    ),
    revision=REVISION,
    case_count=CASE_COUNT,
    build=_build,
    install=_install,
    # Every check is a Judge call over the case rubric, so the loop's cost is real.
    check_surface=CheckSurface(
        check_route=CHECK_SURFACE_ROUTE,
        feedback_intent="feedback",
        expected_check_cost="paid",
    ),
)


def _model_route(model: str) -> str:
    return "/" + model.removeprefix("/")


__all__ = ["HEALTHBENCH_WORST30"]
