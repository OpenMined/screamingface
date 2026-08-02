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
DATASET = "perplexity-ai/draco"
DATASET_REVISION = "ce076749809027649ebd331bcb70f42bf720d387"
PROTOCOL_REVISION = "official-five-pass-v1"
# The paper pins Gemini-3-Pro Preview, which Google shut down on 2026-03-09. Google designated
# Gemini-3.1-Pro Preview as its replacement; the retired API id now resolves to this newer model.
JUDGE_MODEL = "openrouter/google/gemini-3.1-pro-preview"
JUDGE_PASSES = 5
JUDGE_PARAMS = (
    ("temperature", "0.2"),
    ("reasoning", "low"),
    ("max_output_tokens", "4096"),
)
REVISION = hashlib.sha256(
    "\n".join(
        (
            DATASET,
            DATASET_REVISION,
            PROTOCOL_REVISION,
            JUDGE_MODEL,
            str(JUDGE_PASSES),
            repr(JUDGE_PARAMS),
            JUDGE_INSTRUCTIONS,
        )
    ).encode()
).hexdigest()[:16]
ROUTE_PREFIX = f"/benchmarks/{BENCHMARK_ID}/{REVISION}"
CASES_ROUTE = f"{ROUTE_PREFIX}/cases"
TASKS_ROUTE = f"{ROUTE_PREFIX}/tasks"
VERDICT_ROUTE = f"{ROUTE_PREFIX}/criterion-verdict"
AGGREGATE_ROUTE = f"{ROUTE_PREFIX}/aggregate"


def _build(case_count: int) -> Node:
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
                route=VERDICT_ROUTE,
            ),
            name=f"verdict_{run}",
            weight=1.0,
        )
        for run in range(1, JUDGE_PASSES + 1)
    )
    criteria = iterate(
        RelExpr(
            path=TASKS_ROUTE,
            # The Candidate call is the collection call's direct context, so it executes exactly
            # once per case before the returned criterion tasks fan out. No case-row sibling has
            # to cross into the nested criterion map.
            context=render(candidate("$item.input")),
            intent=Text("$item.id"),
        ),
        body=(
            src("$item.criterion_id", name="criterion_id", weight=0.0),
            src("$item.criterion", name="criterion", weight=0.0),
            src("$item.criterion_type", name="criterion_type", weight=0.0),
            *judge_calls,
        ),
        intent=Text("criterion"),
    )
    criterion_results = expr(
        src(criteria, name="criteria", weight=0.0),
        intent=Text("$criteria"),
    )
    rows = iterate(
        CASES_ROUTE,
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
                path=AGGREGATE_ROUTE,
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


def _install(node: Url4Node, assets: Path) -> None:
    # Lazy import keeps the resource-only control-plane path from loading filesystem runtime code.
    from url4_cloud.benchmarks.draco.runtime import install

    install(node, assets)


DRACO = Benchmark(
    id=BENCHMARK_ID,
    title="DRACO",
    description="The 100-task DRACO deep-research benchmark.",
    revision=REVISION,
    case_count=CASE_COUNT,
    required_models=(JUDGE_MODEL,),
    build=_build,
    install=_install,
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
