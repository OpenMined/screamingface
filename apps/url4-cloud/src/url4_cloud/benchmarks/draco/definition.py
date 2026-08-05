"""DRACO as one Engine-owned Benchmark definition."""

from __future__ import annotations

import hashlib
from pathlib import Path

from url4 import Node, RelExpr, Text, expr, iterate, render, src
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark, candidate
from url4_cloud.benchmarks.draco.prompts import JUDGE_INSTRUCTIONS
from url4_cloud.benchmarks.draco.verdict import call as criterion_verdict

BENCHMARK_ID = "draco"
CASE_COUNT = 100
SMOKE_BENCHMARK_ID = "draco/smoke"
SMOKE_CASE_COUNT = 1
DATASET = "perplexity-ai/draco"
DATASET_REVISION = "ce076749809027649ebd331bcb70f42bf720d387"
PROTOCOL_REVISION = "official-five-pass-v1"
SMOKE_PROTOCOL_REVISION = "structural-smoke-v1"
# The paper pins Gemini-3-Pro Preview, which Google shut down on 2026-03-09. Google designated
# Gemini-3.1-Pro Preview as its replacement; the retired API id now resolves to this newer model.
JUDGE_MODEL = "openrouter/google/gemini-3.1-pro-preview"
JUDGE_PASSES = 5
SMOKE_JUDGE_PASSES = 1
SMOKE_CRITERION_COUNT = 1
RETRIEVAL_POLICY_ID = "draco/official"
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
            PROTOCOL_REVISION,
            RETRIEVAL_POLICY_ID,
            repr(EXCLUDED_DOMAINS),
            JUDGE_MODEL,
            str(JUDGE_PASSES),
            repr(JUDGE_PARAMS),
            JUDGE_INSTRUCTIONS,
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
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"
SMOKE_ROUTE_PREFIX = f"/benchmarks/{SMOKE_BENCHMARK_ID}/{SMOKE_REVISION}"
SMOKE_CASES_ROUTE = f"{SMOKE_ROUTE_PREFIX}/cases"
SMOKE_TASKS_ROUTE = f"{SMOKE_ROUTE_PREFIX}/tasks"
SMOKE_VERDICT_ROUTE = f"{SMOKE_ROUTE_PREFIX}/criterion-verdict"
SMOKE_AGGREGATE_ROUTE = f"{SMOKE_ROUTE_PREFIX}/aggregate"


def _build(case_count: int) -> Node:
    return _build_protocol(
        case_count,
        cases_route=CASES_ROUTE,
        tasks_route=TASKS_ROUTE,
        verdict_route=VERDICT_ROUTE,
        aggregate_route=AGGREGATE_ROUTE,
        judge_passes=JUDGE_PASSES,
        criterion_count=None,
    )


def _build_smoke(case_count: int) -> Node:
    return _build_protocol(
        case_count,
        cases_route=SMOKE_CASES_ROUTE,
        tasks_route=SMOKE_TASKS_ROUTE,
        verdict_route=SMOKE_VERDICT_ROUTE,
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
                    params=JUDGE_PARAMS,
                ),
                "$item.criterion_id",
                case_id="$item.case_id",
                route=verdict_route,
            ),
            name=f"verdict_{run}",
            weight=1.0,
        )
        for run in range(1, judge_passes + 1)
    )
    criteria = iterate(
        RelExpr(
            path=tasks_route,
            # The Candidate call is the collection call's direct context, so it executes exactly
            # once per case before the returned criterion tasks fan out. No case-row sibling has
            # to cross into the nested criterion map.
            context=render(
                candidate(
                    "$item.input",
                    web_search=True,
                    web_search_exclude=EXCLUDED_DOMAINS,
                )
            ),
            intent=Text("$item.id"),
        ),
        body=(
            src("$item.criterion_id", name="criterion_id", weight=0.0),
            src("$item.criterion", name="criterion", weight=0.0),
            src("$item.criterion_type", name="criterion_type", weight=0.0),
            *judge_calls,
        ),
        intent=Text("criterion"),
        slice=None if criterion_count is None else (0, criterion_count),
    )
    criterion_results = expr(
        src(criteria, name="criteria", weight=0.0),
        intent=Text("$criteria"),
    )
    rows = iterate(
        cases_route,
        body=(src(criterion_results, name="graded", weight=1.0),),
        intent=Text("case"),
        slice=None if case_count == CASE_COUNT else (0, case_count),
        on_error="collect",
    )
    row_set = expr(
        src(rows, name="selected_rows", weight=0.0),
        intent=Text("$selected_rows"),
    )
    node = expr(
        src(row_set, name="rows", weight=0.0),
        src(
            RelExpr(
                path=aggregate_route,
                # The complete row collection is the wide channel. Keeping it in context means
                # an in-process handler receives it directly and a subprocess adapter would pipe
                # it over stdin; it can never hit the operating system's argv size limit.
                context="$rows",
                intent=Text("aggregate"),
            ),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )
    return node


def _install(node: Url4Node, assets: Path, _model_routes: frozenset[str]) -> None:
    # Lazy import keeps the resource-only control-plane path from loading filesystem runtime code.
    from url4_cloud.benchmarks.draco.runtime import install

    install(node, assets / BENCHMARK_ID)


DRACO = Benchmark(
    id=BENCHMARK_ID,
    variant="canonical",
    title="DRACO",
    description="The 100-task DRACO deep-research benchmark.",
    revision=REVISION,
    case_count=CASE_COUNT,
    build=_build,
    install=_install,
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
    install=_install,
    case_ids=(1,),
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


__all__ = ["DRACO"]
