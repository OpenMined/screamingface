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

    @property
    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "cases_route": self.cases_route,
            "grader": {"kind": self.grader_kind, "route": self.grader_route},
            "aggregator": {
                "kind": self.aggregator_kind,
                "route": self.aggregator_route,
            },
            "tools": list(self.tools),
            "max_tool_calls": self.max_tool_calls,
            "tool_policy_route": self.tool_policy_route,
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


def draco_tool_policy() -> str:
    """Return the immutable portable research policy pinned by draco@1."""

    return json.dumps(DRACO_TOOL_POLICY, allow_nan=False, separators=(",", ":"))


__all__ = [
    "BenchmarkRoute",
    "DRACO_TOOL_POLICY",
    "DRACO_TOOL_POLICY_ROUTE",
    "GPQA_CASES_ROUTE",
    "GPQA_ID",
    "GPQA_TITLE",
    "draco_tool_policy",
    "gpqa_cases",
]
