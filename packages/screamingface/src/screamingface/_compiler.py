"""Compile one flat Model Candidate Benchmark URL4 for SF Engine."""

from __future__ import annotations

from url4 import RelExpr, Text, iterate, render, src, struct

from screamingface._benchmark_manifest import _BenchmarkManifest
from screamingface.model import Model


def compile_model_benchmark(
    model: Model,
    manifest: _BenchmarkManifest,
    *,
    limit: int | None,
) -> str:
    """Compile cases → answer → grade → aggregate into one canonical URL4."""

    parameters = tuple(
        (name, _parameter(value))
        for name, value in (
            ("temperature", model.temperature),
            ("reasoning", model.reasoning),
            ("max_output_tokens", model.max_output_tokens),
        )
        if value is not None
    )
    instructions = model.instructions or "Answer the benchmark question completely."
    body = (
        src("$item.input", name="question", weight=0.0),
        src(
            RelExpr(
                path="/" + model.model.removeprefix("/"),
                context="$question",
                intent=Text(_url4_text(instructions)),
                params=parameters,
            ),
            name="answer",
            weight=0.0,
        ),
        src(
            struct(
                {
                    "schema": "screamingface.recipe-result.v1",
                    "answer": "$answer",
                }
            ),
            name="candidate_result",
            weight=0.0,
        ),
        src(
            struct(
                {
                    "benchmark_id": manifest.info.id,
                    "case_id": "$item.id",
                    "question": "$question",
                    "reference": "$item.reference",
                }
            ),
            name="grade_input",
            weight=0.0,
        ),
        src(
            RelExpr(
                path=manifest.grader_route,
                context="$candidate_result",
                intent=Text("$grade_input"),
            ),
            name="case_result",
            weight=0.0,
        ),
    )
    reducer = render(
        RelExpr(
            path=manifest.aggregator_route,
            intent=Text("Aggregate DRACO-Lite case grades."),
        )
    )
    return render(
        iterate(
            manifest.cases_route,
            body=body,
            intent=Text("$case_result"),
            reduce=reducer,
            slice=None if limit is None else (0, limit),
            on_error="fail",
        )
    )


def _parameter(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _url4_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\u2028").replace("\t", " ")
    unsupported = next(
        (character for character in normalized if character < " " or character == "\x7f"),
        None,
    )
    if unsupported is not None:
        raise ValueError(
            f"URL4 text contains unsupported control character U+{ord(unsupported):04X}"
        )
    return normalized.replace("$", "$$")


__all__: list[str] = []
