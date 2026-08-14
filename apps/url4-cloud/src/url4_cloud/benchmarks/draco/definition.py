"""DRACO as one Engine-owned Benchmark definition."""

from __future__ import annotations

import hashlib
from pathlib import Path

from url4 import Node, RelExpr, Text, expr, iterate, render, src, struct
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA
from url4_cloud.benchmarks.definition import Benchmark, CheckSurface, candidate
from url4_cloud.benchmarks.draco.check_policy import CHECK_CRITERION
from url4_cloud.benchmarks.draco.prompts import JUDGE_INSTRUCTIONS
from url4_cloud.benchmarks.draco.verdict import call as criterion_verdict
from url4_cloud.benchmarks.protocol import (
    EVALUATION_PROTOCOL_REVISION,
    build_evaluation_protocol,
)

BENCHMARK_ID = "draco"
CASE_COUNT = 100
LITE_BENCHMARK_ID = "draco/lite"
# Two most represented pinned-data domains; within each, choose the Case nearest the global
# median rubric size (38 criteria), breaking ties by Case id. Order follows domain prevalence.
LITE_CASE_IDS = (2, 15)
LITE_CASE_COUNT = len(LITE_CASE_IDS)
LITE_CRITERION_COUNT = 10
LITE_CRITERION_SELECTION = "axis-balanced"
SMOKE_BENCHMARK_ID = "draco/smoke"
SMOKE_CASE_COUNT = 1
DATASET = "perplexity-ai/draco"
DATASET_REVISION = "ce076749809027649ebd331bcb70f42bf720d387"
DATASET_PREPARER_REVISION = "datasets-5.0.0"
PROTOCOL_REVISION = "five-pass-reproduction-v1"
LITE_PROTOCOL_REVISION = "balanced-lite-v1"
SMOKE_PROTOCOL_REVISION = "structural-smoke-v1"
# The paper pins Gemini-3-Pro Preview, which Google shut down on 2026-03-09. Google designated
# Gemini-3.1-Pro Preview as its replacement, so this reproduction uses that successor model.
JUDGE_MODEL = "openrouter/google/gemini-3.1-pro-preview"
JUDGE_PASSES = 5
JUDGE_SEEDS = tuple(range(1, JUDGE_PASSES + 1))
LITE_JUDGE_PASSES = 1
SMOKE_JUDGE_PASSES = 1
SMOKE_CRITERION_COUNT = 1
RETRIEVAL_POLICY_ID = "draco/reproduction"
EXCLUDED_DOMAINS = (
    "arxiv.org",
    "huggingface.co",
    "openrouter.ai",
    "paperswithcode.com",
    "alphaxiv.org",
    "semanticscholar.org",
    "research.perplexity.ai",
)
JUDGE_PARAMS = (
    # The same model is also a DRACO Candidate. Its route can retrieve, but Grading cannot. The
    # Runner consumes this control and sends no search field or tools to AI Gateway, so the Judge
    # request remains eligible for the exact-response cache.
    ("web_search", "false"),
    ("temperature", "0.2"),
    # The official low-reasoning setting is added once AI Gateway exposes a validated
    # OpenRouter parameter for it. Unknown fields fail closed, so guessing here breaks every
    # judge call rather than producing a documented protocol deviation.
    ("max_tokens", "4096"),
)
REVISION = hashlib.sha256(
    "\n".join(
        (
            DATASET,
            DATASET_REVISION,
            DATASET_PREPARER_REVISION,
            PROTOCOL_REVISION,
            EVALUATION_PROTOCOL_REVISION,
            CANDIDATE_RESULT_SCHEMA,
            RETRIEVAL_POLICY_ID,
            repr(EXCLUDED_DOMAINS),
            JUDGE_MODEL,
            str(JUDGE_PASSES),
            repr(JUDGE_SEEDS),
            repr(JUDGE_PARAMS),
            JUDGE_INSTRUCTIONS,
        )
    ).encode()
).hexdigest()[:16]
LITE_REVISION = hashlib.sha256(
    "\n".join(
        (
            REVISION,
            LITE_PROTOCOL_REVISION,
            repr(LITE_CASE_IDS),
            str(LITE_CRITERION_COUNT),
            LITE_CRITERION_SELECTION,
            str(LITE_JUDGE_PASSES),
        )
    ).encode()
).hexdigest()[:16]
SMOKE_REVISION = hashlib.sha256(
    "\n".join(
        (
            REVISION,
            SMOKE_PROTOCOL_REVISION,
            str(SMOKE_CASE_COUNT),
            str(SMOKE_CRITERION_COUNT),
            str(SMOKE_JUDGE_PASSES),
        )
    ).encode()
).hexdigest()[:16]
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
CASES_ROUTE = f"{ROUTE_PREFIX}/cases"
TASKS_ROUTE = f"{ROUTE_PREFIX}/tasks"
VERDICT_ROUTE = f"{ROUTE_PREFIX}/criterion-verdict"
CRITERION_EVALUATION_ROUTE = f"{ROUTE_PREFIX}/criterion-evaluation"
CASE_EVALUATION_ROUTE = f"{ROUTE_PREFIX}/case-evaluation"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"
# The mid-run check surface (OME-829). The pass criterion is protocol semantics, so it
# rides in the path: a different criterion is a different route, visible in the manifest
# and in every Candidate url4 compiled against it.
CHECK_SURFACE_ROUTE = f"{ROUTE_PREFIX}/check-surface/{CHECK_CRITERION}"
LITE_ROUTE_PREFIX = f"/benchmarks/{LITE_BENCHMARK_ID}/{LITE_REVISION}"
LITE_CASES_ROUTE = f"{LITE_ROUTE_PREFIX}/cases"
LITE_TASKS_ROUTE = f"{LITE_ROUTE_PREFIX}/tasks"
LITE_VERDICT_ROUTE = f"{LITE_ROUTE_PREFIX}/criterion-verdict"
LITE_CRITERION_EVALUATION_ROUTE = f"{LITE_ROUTE_PREFIX}/criterion-evaluation"
LITE_CASE_EVALUATION_ROUTE = f"{LITE_ROUTE_PREFIX}/case-evaluation"
LITE_AGGREGATE_ROUTE = f"{LITE_ROUTE_PREFIX}/aggregate"
LITE_CHECK_SURFACE_ROUTE = f"{LITE_ROUTE_PREFIX}/check-surface/{CHECK_CRITERION}"
SMOKE_ROUTE_PREFIX = f"/benchmarks/{SMOKE_BENCHMARK_ID}/{SMOKE_REVISION}"
SMOKE_CASES_ROUTE = f"{SMOKE_ROUTE_PREFIX}/cases"
SMOKE_TASKS_ROUTE = f"{SMOKE_ROUTE_PREFIX}/tasks"
SMOKE_VERDICT_ROUTE = f"{SMOKE_ROUTE_PREFIX}/criterion-verdict"
SMOKE_CRITERION_EVALUATION_ROUTE = f"{SMOKE_ROUTE_PREFIX}/criterion-evaluation"
SMOKE_CASE_EVALUATION_ROUTE = f"{SMOKE_ROUTE_PREFIX}/case-evaluation"
SMOKE_AGGREGATE_ROUTE = f"{SMOKE_ROUTE_PREFIX}/aggregate"
SMOKE_CHECK_SURFACE_ROUTE = f"{SMOKE_ROUTE_PREFIX}/check-surface/{CHECK_CRITERION}"


def _build(case_count: int) -> Node:
    return _build_protocol(
        case_count,
        cases_route=CASES_ROUTE,
        tasks_route=TASKS_ROUTE,
        verdict_route=VERDICT_ROUTE,
        criterion_evaluation_route=CRITERION_EVALUATION_ROUTE,
        case_evaluation_route=CASE_EVALUATION_ROUTE,
        aggregate_route=AGGREGATE_ROUTE,
        judge_passes=JUDGE_PASSES,
        criterion_count=None,
    )


def _build_lite(case_count: int) -> Node:
    return _build_protocol(
        case_count,
        cases_route=LITE_CASES_ROUTE,
        tasks_route=LITE_TASKS_ROUTE,
        verdict_route=LITE_VERDICT_ROUTE,
        criterion_evaluation_route=LITE_CRITERION_EVALUATION_ROUTE,
        case_evaluation_route=LITE_CASE_EVALUATION_ROUTE,
        aggregate_route=LITE_AGGREGATE_ROUTE,
        judge_passes=LITE_JUDGE_PASSES,
        criterion_count=LITE_CRITERION_COUNT,
    )


def _build_smoke(case_count: int) -> Node:
    return _build_protocol(
        case_count,
        cases_route=SMOKE_CASES_ROUTE,
        tasks_route=SMOKE_TASKS_ROUTE,
        verdict_route=SMOKE_VERDICT_ROUTE,
        criterion_evaluation_route=SMOKE_CRITERION_EVALUATION_ROUTE,
        case_evaluation_route=SMOKE_CASE_EVALUATION_ROUTE,
        aggregate_route=SMOKE_AGGREGATE_ROUTE,
        judge_passes=SMOKE_JUDGE_PASSES,
        criterion_count=SMOKE_CRITERION_COUNT,
    )


def _build_protocol(
    case_count: int,
    *,
    cases_route: str,
    tasks_route: str,
    verdict_route: str,
    criterion_evaluation_route: str,
    case_evaluation_route: str,
    aggregate_route: str,
    judge_passes: int,
    criterion_count: int | None,
) -> Node:
    judge_calls = tuple(
        src(
            criterion_verdict(
                RelExpr(
                    path=_model_route(JUDGE_MODEL),
                    # Every dynamic value is local to this iteration item. The model sees only
                    # the official prompt fields; the Engine binds the known criterion id after
                    # the reply, so grading never trusts a model-generated identifier.
                    context=_judge_context(),
                    intent=Text(_url4_text(JUDGE_INSTRUCTIONS)),
                    # Stable pass seeds create five independent cache slots. Repeated benchmark
                    # runs may reuse those slots, but one run can never collapse five Judge
                    # passes into one cached response.
                    params=(*JUDGE_PARAMS, ("seed", str(run))),
                ),
                "$item.criterion_id",
                case_id="$item.case_id",
                sequence=run,
                route=verdict_route,
            ),
            name=f"verdict_{run}",
            weight=0.0,
        )
        for run in range(1, judge_passes + 1)
    )
    criterion_evaluation = expr(
        src("$item.case_record", name="case_record", weight=0.0),
        src("$item.check_record", name="check_record", weight=0.0),
        *judge_calls,
        src(
            RelExpr(
                path=criterion_evaluation_route,
                context=render(
                    struct(
                        {
                            "case": "$case_record",
                            "check": "$check_record",
                            **{
                                f"evidence_{run}": f"$verdict_{run}"
                                for run in range(1, judge_passes + 1)
                            },
                        }
                    )
                ),
                intent=Text("$item.case_id"),
            ),
            name="criterion_evaluation",
            weight=0.0,
        ),
        intent=Text("$criterion_evaluation"),
    )
    criteria = iterate(
        RelExpr(
            path=tasks_route,
            # This collection boundary invokes the Candidate exactly once, then returns the
            # criterion tasks plus Engine-bound Case/Check records for lossless aggregation.
            context=render(
                candidate(
                    "$item.input",
                    web_search=True,
                    web_search_exclude=EXCLUDED_DOMAINS,
                )
            ),
            intent=Text("$item.id"),
        ),
        body=(src(criterion_evaluation, name="evaluated", weight=0.0),),
        intent=Text("$evaluated"),
        slice=None if criterion_count is None else (0, criterion_count),
    )
    case_evaluation = expr(
        src(criteria, name="criteria", weight=0.0),
        src(
            RelExpr(
                path=case_evaluation_route,
                context="$criteria",
                intent=Text("$item.id"),
            ),
            name="case_evaluation",
            weight=0.0,
        ),
        intent=Text("$case_evaluation"),
    )
    return build_evaluation_protocol(
        cases_route=cases_route,
        case_evaluation=case_evaluation,
        selected_case_count=case_count,
        available_case_count=CASE_COUNT,
        aggregate_route=aggregate_route,
    )


def _install_canonical(node: Url4Node, assets: Path) -> None:
    # Lazy import keeps the resource-only control-plane path from loading filesystem runtime code.
    from url4_cloud.benchmarks.draco.runtime import install_canonical

    install_canonical(node, assets / BENCHMARK_ID)


def _install_lite(node: Url4Node, assets: Path) -> None:
    from url4_cloud.benchmarks.draco.runtime import install_lite

    install_lite(node, assets / BENCHMARK_ID)


def _install_smoke(node: Url4Node, assets: Path) -> None:
    from url4_cloud.benchmarks.draco.runtime import install_smoke

    install_smoke(node, assets / BENCHMARK_ID)


def _check_surface(route: str) -> CheckSurface:
    """Every DRACO variant checks the same way and every check is a judge call."""

    return CheckSurface(
        check_route=route,
        feedback_intent="feedback",
        expected_check_cost="paid",
    )


DRACO = Benchmark(
    id=BENCHMARK_ID,
    variant="canonical",
    title="DRACO",
    description=(
        "A 100-task DRACO reproduction with official score arithmetic. It uses the successor "
        "Judge model, provider-default reasoning, mixed native/Tavily retrieval, and a host-only "
        "approximation of the reference blocklist, so its scores are not paper-identical."
    ),
    revision=REVISION,
    case_count=CASE_COUNT,
    build=_build,
    install=_install_canonical,
    check_surface=_check_surface(CHECK_SURFACE_ROUTE),
)

DRACO_LITE = Benchmark(
    id=LITE_BENCHMARK_ID,
    variant="lite",
    title="DRACO Lite",
    description=(
        "A two-Case directional preview using an axis-balanced selection of ten criteria per "
        "Case and one Judge pass per criterion. Its score is not comparable to canonical DRACO."
    ),
    revision=LITE_REVISION,
    case_count=LITE_CASE_COUNT,
    build=_build_lite,
    install=_install_lite,
    check_surface=_check_surface(LITE_CHECK_SURFACE_ROUTE),
)

DRACO_SMOKE = Benchmark(
    id=SMOKE_BENCHMARK_ID,
    variant="smoke",
    title="DRACO Structural Smoke",
    description=(
        "A one-Case, one-criterion, one-Judge-pass structural probe. Its score is diagnostic "
        "and not comparable to canonical DRACO."
    ),
    revision=SMOKE_REVISION,
    case_count=SMOKE_CASE_COUNT,
    build=_build_smoke,
    install=_install_smoke,
    check_surface=_check_surface(SMOKE_CHECK_SURFACE_ROUTE),
)


def _model_route(model: str) -> str:
    return "/" + model.removeprefix("/")


def _judge_context() -> str:
    return " ".join(
        (
            "<criterion_type>",
            "$item.criterion_type",
            "</criterion_type>",
            "<criterion>",
            "$item.criterion",
            "</criterion>",
            "<query>",
            "$item.question",
            "</query>",
            "<response>",
            "$item.answer",
            "</response>",
        )
    )


def _url4_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\u2028").replace("\t", " ")
    unsupported = next(
        (character for character in normalized if character < " " or character == "\x7f"),
        None,
    )
    if unsupported is not None:
        raise ValueError(
            f"Benchmark prompt contains unsupported control character U+{ord(unsupported):04X}"
        )
    return normalized.replace("$", "$$")


__all__ = ["DRACO", "DRACO_LITE", "DRACO_SMOKE"]
