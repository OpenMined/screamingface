"""DRACO Lite as one Engine-owned Benchmark definition."""

from __future__ import annotations

from url4 import RelExpr, Text, expr, iterate, render, src, struct
from url4_cloud.benchmarks.base import Benchmark, BenchmarkExpression, candidate
from url4_cloud.benchmarks.draco.prompts import JUDGE_INSTRUCTIONS

BENCHMARK_ID = "draco-lite"
CASE_COUNT = 100
CASES_ROUTE = "/draco/cases"
CRITERIA_ROUTE = "/draco/criteria/{case_id}"
AGGREGATE_ROUTE = "/benchmark"
JUDGE_MODEL = "openrouter/google/gemini-3.1-pro-preview"
JUDGE_PASSES = 3
JUDGE_PARAMS = (
    ("temperature", "0.2"),
    ("reasoning", "low"),
    ("max_output_tokens", "4096"),
)


def _build(case_count: int) -> BenchmarkExpression:
    judge_runs = iterate(
        tuple(str(run) for run in range(1, JUDGE_PASSES + 1)),
        body=(
            src(
                RelExpr(
                    path=_model_route(JUDGE_MODEL),
                    context=_structured_context(
                        {
                            "answer": "$answer",
                            "criterion_id": "$criterion_id",
                            "criterion": "$criterion",
                        }
                    ),
                    intent=Text(_url4_text(JUDGE_INSTRUCTIONS)),
                    params=JUDGE_PARAMS,
                ),
                name="verdict",
                weight=0.0,
            ),
            # Prevent an all-call row from being reduced through the world's default model.
            src("$item", name="pass", weight=0.0),
        ),
        intent=Text("$verdict"),
    )
    judge_results = expr(
        src(judge_runs, name="judge_passes", weight=0.0),
        intent=Text("$judge_passes"),
    )
    criteria = iterate(
        CRITERIA_ROUTE.replace("{case_id}", "$item.id"),
        body=(
            src("$item.id", name="criterion_id", weight=0.0),
            src("$item.requirement", name="criterion", weight=0.0),
            src(judge_results, name="runs", weight=1.0),
        ),
        intent=Text("criterion"),
    )
    criterion_results = expr(
        src(criteria, name="criteria", weight=0.0),
        intent=Text("$criteria"),
    )
    rows = iterate(
        CASES_ROUTE,
        body=(
            src("$item.input", name="question", weight=0.0),
            src(candidate("$question"), name="answer", weight=0.0),
            src(criterion_results, name="graded", weight=1.0),
        ),
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
                context="aggregate",
                intent=Text("$rows"),
            ),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )
    return BenchmarkExpression(
        node=node,
        candidate_invocations=case_count,
    )


DRACO_LITE = Benchmark(
    id=BENCHMARK_ID,
    title="DRACO Lite",
    description="Research-quality rubric evaluation.",
    case_count=CASE_COUNT,
    primary_metric="normalized_score",
    score_direction="maximize",
    required_models=(JUDGE_MODEL,),
    candidate_capabilities=("web_search", "web_fetch"),
    runtime_capabilities=(),
    build=_build,
)


def _structured_context(value: dict[str, object]) -> str:
    return render(src(struct(value), name="payload"))


def _model_route(model: str) -> str:
    return "/" + model.removeprefix("/")


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


__all__ = ["DRACO_LITE"]
