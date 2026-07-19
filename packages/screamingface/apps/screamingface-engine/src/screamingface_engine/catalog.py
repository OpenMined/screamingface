"""Canonical ScreamingFace registry, manifests, and Hugging Face case loaders."""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from screamingface import Benchmark, Case, aggregators, graders
from screamingface.draco import _JUDGE_SYSTEM_PROMPT

from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE

type CaseLoader = Callable[[], Iterable[Case]]


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """One public URL4 model route and its private AI Gateway model id."""

    id: str
    gateway_model: str
    supported_tools: tuple[str, ...] = ()

    @property
    def route(self) -> str:
        return f"/{self.id}"


MODEL_ROUTES = (
    ModelRoute("codex/gpt-5.5", "codex/gpt-5.5"),
    ModelRoute("gemini/2.5", "gemini-cli/gemini-2.5-pro"),
    ModelRoute("claude/sonnet-4.6", "anthropic/claude-sonnet-4-6"),
)


@dataclass(frozen=True, slots=True)
class PublishedBenchmark:
    benchmark: Benchmark
    cases_path: str
    loader: CaseLoader


def gpqa_cases() -> Iterable[Case]:
    """Load and normalize canonical GPQA Diamond cases."""

    from datasets import load_dataset

    rows = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")
    for index, raw_row in enumerate(rows):
        row = cast(Mapping[str, object], raw_row)
        case_id = f"gpqa-diamond-{index}"
        correct = str(row["Correct Answer"])
        options = [
            correct,
            *(str(row[f"Incorrect Answer {number}"]) for number in range(1, 4)),
        ]
        random.Random(f"screamingface:gpqa@1:{case_id}").shuffle(options)
        rendered = "\n".join(
            f"{chr(65 + option_index)}. {option}" for option_index, option in enumerate(options)
        )
        yield Case(
            case_id,
            f"{row['Question']}\n\n{rendered}\n\nReply with only A, B, C, or D.",
            reference=chr(65 + options.index(correct)),
            metadata={"subject": "science"},
        )


def draco_cases() -> Iterable[Case]:
    """Load and normalize canonical DRACO research cases."""

    from datasets import load_dataset

    rows = load_dataset("perplexity-ai/draco", split="test")
    for index, raw_row in enumerate(rows):
        row = cast(Mapping[str, object], raw_row)
        raw_reference = row.get("answer")
        reference = json.loads(raw_reference) if isinstance(raw_reference, str) else raw_reference
        metadata = _json_object(row.get("metadata"))
        domain = row.get("domain") or metadata.get("domain") or "unknown"
        yield Case(
            str(row.get("id") or f"draco-{index}"),
            str(row.get("problem") or row.get("question") or ""),
            reference=reference,
            metadata={"domain": str(domain)},
        )


def published_benchmarks(
    case_loaders: Mapping[str, CaseLoader] | None = None,
) -> tuple[PublishedBenchmark, ...]:
    """Build canonical definitions while allowing isolated tests to replace dataset I/O."""

    loaders = {"gpqa@1": gpqa_cases, "draco@1": draco_cases}
    if case_loaders is not None:
        unknown = set(case_loaders) - set(loaders)
        if unknown:
            raise ValueError(f"unknown benchmark case loader(s): {sorted(unknown)}")
        loaders.update(case_loaders)
    gpqa = Benchmark(
        "gpqa@1",
        title="GPQA Diamond",
        cases=loaders["gpqa@1"],
        grader=graders.ExactChoice(),
        aggregator=aggregators.Mean(),
    )
    draco = Benchmark(
        "draco@1",
        title="DRACO",
        cases=loaders["draco@1"],
        grader=graders.Rubric(
            model="gemini/3.1-pro-preview",
            prompt=_JUDGE_SYSTEM_PROMPT,
            passes=5,
            params={"temperature": 0.2, "reasoning": "low", "max_tokens": 4096},
        ),
        aggregator=aggregators.Mean(),
        tools=("web_search",),
    )
    return (
        PublishedBenchmark(gpqa, "/benchmarks/gpqa@1/cases", loaders["gpqa@1"]),
        PublishedBenchmark(draco, "/benchmarks/draco@1/cases", loaders["draco@1"]),
    )


def registry_document(publications: tuple[PublishedBenchmark, ...]) -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.fusion-result.v1"],
        "models": [
            {"id": model.id, "supported_tools": list(model.supported_tools)}
            for model in MODEL_ROUTES
        ],
        "reducers": [{"id": "majority_vote", "route": MAJORITY_VOTE_ROUTE}],
        "benchmarks": [
            {
                "id": publication.benchmark.id,
                "manifest": f"/benchmarks/{publication.benchmark.id}",
                "tools": list(publication.benchmark.tools),
            }
            for publication in publications
        ],
    }


def manifest_document(publication: PublishedBenchmark) -> dict[str, object]:
    benchmark = publication.benchmark
    return {
        "schema": "screamingface.benchmark.v1",
        "id": benchmark.id,
        "title": benchmark.title,
        "tools": list(benchmark.tools),
        "cases": {"url": publication.cases_path, "format": "ndjson"},
        "grader": _grader_document(benchmark.grader),
        "aggregator": {"type": benchmark.aggregator.kind},
    }


def cases_document(publication: PublishedBenchmark) -> str:
    cases = publication.benchmark._materialize_cases()
    return "".join(f"{json.dumps(case._to_wire(), separators=(',', ':'))}\n" for case in cases)


def _grader_document(grader: graders.Grader) -> dict[str, object]:
    if isinstance(grader, graders.ExactChoice):
        return {"type": grader.kind}
    if isinstance(grader, graders.Rubric):
        return {
            "type": grader.kind,
            "model": grader.model,
            "prompt": grader.prompt,
            "passes": grader.passes,
            "params": grader.params,
        }
    raise TypeError(f"unsupported grader: {type(grader).__name__}")


def _json_object(value: Any) -> dict[str, object]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}
