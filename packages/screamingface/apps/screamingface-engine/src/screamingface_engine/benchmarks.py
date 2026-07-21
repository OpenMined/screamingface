"""Canonical benchmark collections published through the ScreamingFace URL4 node."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from url4 import ResolutionError

GPQA_ID = "gpqa@1"
GPQA_TITLE = "GPQA Diamond"
GPQA_CASES_ROUTE = "/benchmarks/gpqa/1/cases"


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
    max_tool_rounds: int | None = None

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
            "max_tool_rounds": self.max_tool_rounds,
        }


def gpqa_cases() -> str:
    """Return the pinned GPQA Diamond rows as an NDJSON URL4 collection."""

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
    return "\n".join(
        json.dumps(case._to_wire(), allow_nan=False, separators=(",", ":")) for case in cases
    )


__all__ = [
    "BenchmarkRoute",
    "GPQA_CASES_ROUTE",
    "GPQA_ID",
    "GPQA_TITLE",
    "gpqa_cases",
]
