"""Canonical benchmark collections published through the ScreamingFace URL4 node."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from url4 import ResolutionError

from screamingface_engine.evaluation_events import emit_progress

GPQA_ID = "gpqa@1"
GPQA_TITLE = "GPQA Diamond"
GPQA_CASES_ROUTE = "/benchmarks/gpqa/1/cases"
DRACO_ID = "draco@1"
DRACO_TITLE = "DRACO"
DRACO_CASES_ROUTE = "/benchmarks/draco/1/cases"
DRACO_LITE_ID = "draco-lite@1"
DRACO_LITE_TITLE = "DRACO Lite"
DRACO_LITE_CASES_ROUTE = "/benchmarks/draco-lite/1/cases"
DRACO_LITE_CANDIDATE_ROUTE = "/benchmarks/draco-lite/1/evaluate-candidates"
DRACO_PREVIEW_ID = "draco-preview@1"
DRACO_PREVIEW_TITLE = "DRACO Preview"
DRACO_PREVIEW_CASES_ROUTE = "/benchmarks/draco-preview/1/cases"
DRACO_TOOL_POLICY_ROUTE = "/benchmarks/draco/1/tool-policy"

DRACO_TOOL_POLICY = {
    "schema": "screamingface.tool-policy.v1",
    "tools": ["web_search", "web_fetch"],
    "max_calls": 12,
    "web_search": {
        "max_results": 5,
        "include_domains": [],
        "exclude_domains": [
            "huggingface.co/datasets/perplexity-ai/draco",
            "openrouter.ai/blog/announcements/fusion-beats-frontier",
            "paperswithcode.com/dataset/draco",
            "arxiv.org/abs/2509",
        ],
    },
}


@dataclass(frozen=True, slots=True)
class BenchmarkRoute:
    """One public benchmark manifest and its executable case collection."""

    id: str
    title: str
    cases_route: str
    grader_kind: str
    grader_route: str
    aggregator_kind: str
    aggregator_route: str
    tools: tuple[str, ...] = ()
    max_tool_calls: int | None = None
    tool_policy_route: str | None = None
    grader_config: tuple[tuple[str, object], ...] = ()
    candidate_route: str | None = None
    candidate_aggregator_route: str | None = None

    def __post_init__(self) -> None:
        if self.tools:
            if (
                isinstance(self.max_tool_calls, bool)
                or not isinstance(self.max_tool_calls, int)
                or not 1 <= self.max_tool_calls <= 32
            ):
                raise ValueError(
                    "tool-enabled benchmark max_tool_calls must be an integer from 1 to 32"
                )
            if (
                not isinstance(self.tool_policy_route, str)
                or not self.tool_policy_route.startswith("/")
                or self.tool_policy_route.startswith("//")
                or "?" in self.tool_policy_route
                or "#" in self.tool_policy_route
            ):
                raise ValueError("tool-enabled benchmark requires a same-engine tool policy route")
        elif self.max_tool_calls is not None or self.tool_policy_route is not None:
            raise ValueError("tool-free benchmark cannot declare a tool policy")
        if (self.candidate_route is None) != (self.candidate_aggregator_route is None):
            raise ValueError("benchmark candidate routes must both be configured or both be null")

    @property
    def public(self) -> dict[str, object]:
        grader: dict[str, object] = {"kind": self.grader_kind, "route": self.grader_route}
        grader.update(dict(self.grader_config))
        return {
            "id": self.id,
            "title": self.title,
            "cases_route": self.cases_route,
            "grader": grader,
            "aggregator": {
                "kind": self.aggregator_kind,
                "route": self.aggregator_route,
            },
            "tools": list(self.tools),
            "max_tool_calls": self.max_tool_calls,
            "tool_policy_route": self.tool_policy_route,
            "candidate_route": self.candidate_route,
            "candidate_aggregator_route": self.candidate_aggregator_route,
        }


def gpqa_cases() -> str:
    """Return the pinned GPQA Diamond rows as an NDJSON URL4 collection."""

    emit_progress("dataset", "started", "Loading GPQA Diamond cases")
    if not os.environ.get("HF_TOKEN", "").strip():
        raise ResolutionError(
            "gpqa@1 requires HF_TOKEN in the ScreamingFace engine environment",
            code="dataset_authentication_required",
            permanent=True,
        )
    try:
        from screamingface._benchmarks.gpqa import gpqa_cases as load_gpqa_cases

        cases = load_gpqa_cases()
    except ResolutionError:
        raise
    except Exception as exc:
        raise ResolutionError(
            "the ScreamingFace engine could not load gpqa@1 from Hugging Face",
            code="dataset_unavailable",
        ) from exc
    emit_progress("dataset", "completed", f"Loaded {len(cases)} GPQA Diamond cases")
    return "\n".join(
        json.dumps(case._to_wire(), allow_nan=False, separators=(",", ":")) for case in cases
    )


def draco_cases() -> str:
    """Return the byte-pinned, fully validated DRACO rows as NDJSON."""

    return _draco_rows(preview=False)


def draco_lite_cases() -> str:
    """Return one real DRACO case with ten section-diverse criteria."""

    return _draco_rows(lite=True)


def draco_preview_cases() -> str:
    """Return real DRACO rows reduced to one positive criterion for a cheap walkthrough."""

    return _draco_rows(preview=True)


def _draco_rows(*, preview: bool = False, lite: bool = False) -> str:
    if preview and lite:
        raise ValueError("DRACO rows cannot be both preview and lite")
    if preview:
        benchmark_id, title = DRACO_PREVIEW_ID, DRACO_PREVIEW_TITLE
    elif lite:
        benchmark_id, title = DRACO_LITE_ID, DRACO_LITE_TITLE
    else:
        benchmark_id, title = DRACO_ID, DRACO_TITLE
    emit_progress("dataset", "started", f"Loading {title} cases")
    if not os.environ.get("HF_TOKEN", "").strip():
        raise ResolutionError(
            f"{benchmark_id} requires HF_TOKEN in the ScreamingFace engine environment",
            code="dataset_authentication_required",
            permanent=True,
        )
    try:
        if preview:
            from screamingface._benchmarks.draco_preview import (
                draco_preview_cases as load_cases,
            )
        elif lite:
            from screamingface._benchmarks.draco_lite import draco_lite_cases as load_cases
        else:
            from screamingface._benchmarks.draco import draco_cases as load_cases

        cases = load_cases()
    except ResolutionError:
        raise
    except Exception as exc:
        raise ResolutionError(
            f"the ScreamingFace engine could not load {benchmark_id} from Hugging Face",
            code="dataset_unavailable",
        ) from exc
    emit_progress("dataset", "completed", f"Loaded {len(cases)} {title} cases")
    return "\n".join(
        json.dumps(case._to_wire(), allow_nan=False, separators=(",", ":")) for case in cases
    )


def draco_tool_policy() -> str:
    """Return the immutable portable research policy pinned by draco@1."""

    return json.dumps(DRACO_TOOL_POLICY, allow_nan=False, separators=(",", ":"))


__all__ = [
    "BenchmarkRoute",
    "DRACO_CASES_ROUTE",
    "DRACO_ID",
    "DRACO_LITE_CASES_ROUTE",
    "DRACO_LITE_CANDIDATE_ROUTE",
    "DRACO_LITE_ID",
    "DRACO_LITE_TITLE",
    "DRACO_PREVIEW_CASES_ROUTE",
    "DRACO_PREVIEW_ID",
    "DRACO_PREVIEW_TITLE",
    "DRACO_TITLE",
    "DRACO_TOOL_POLICY",
    "DRACO_TOOL_POLICY_ROUTE",
    "GPQA_CASES_ROUTE",
    "GPQA_ID",
    "GPQA_TITLE",
    "draco_tool_policy",
    "draco_cases",
    "draco_lite_cases",
    "draco_preview_cases",
    "gpqa_cases",
]
