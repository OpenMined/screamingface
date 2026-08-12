"""HealthBench definitions — registry, revisions, and the expression contract.

INVARIANT under test: the exam's protocol identity (template bytes, judge pinning,
subset, scoring rule) is frozen into the revision and the rendered expression — any
drift must fail here before it can ship a different exam under the same name.
"""

from __future__ import annotations

import hashlib

from url4.core.grammar import parse
from url4_cloud.benchmarks.builtins import BUILTIN_BENCHMARKS
from url4_cloud.benchmarks.healthbench.definition import (
    HEALTHBENCH_WORST30,
    JUDGE_MODEL,
    REVISION,
)
from url4_cloud.benchmarks.healthbench.prompts import GRADER_TEMPLATE
from url4_cloud.benchmarks.healthbench.subset import WORST30_CASE_IDS, WORST30_HF_IDS

# WHY: byte-parity with OpenAI simple-evals' GRADER_TEMPLATE (verified against the
# vendored reference at authoring time). Any edit — even fixing the reference's own
# typos — breaks grading parity and must be a deliberate protocol revision.
GRADER_TEMPLATE_SHA = "2adffd51fd259554ebcd036ad1072d4aa2b7ce3aec2bbffe36271f911632ed3c"


def _url4(benchmark, limit=None) -> str:
    value = benchmark.resource(limit)["url4"]
    assert isinstance(value, str)
    return value


def test_the_grader_template_is_byte_pinned() -> None:
    assert hashlib.sha256(GRADER_TEMPLATE.encode()).hexdigest() == GRADER_TEMPLATE_SHA


def test_the_exam_is_registered_under_its_id() -> None:
    assert BUILTIN_BENCHMARKS.get("healthbench/worst30") is HEALTHBENCH_WORST30


def test_the_subset_is_the_frozen_157() -> None:
    assert len(WORST30_HF_IDS) == 157
    assert len(set(WORST30_HF_IDS)) == 157
    assert len(WORST30_CASE_IDS) == 157


def test_the_exam_routes_are_revision_pinned() -> None:
    assert REVISION in _url4(HEALTHBENCH_WORST30)


def test_the_expression_renders_and_reparses() -> None:
    rendered = _url4(HEALTHBENCH_WORST30)
    parse(rendered)
    # S-RT1: the whole exam must stay far under transport-hostile sizes — the
    # per-item fan-out is built Engine-side, not pre-expanded into the address.
    assert len(rendered) < 4_000


def test_the_judge_call_shape_is_the_official_one() -> None:
    rendered = _url4(HEALTHBENCH_WORST30)
    # Empty intent — the Runner maps a non-empty intent to a SYSTEM message and the
    # official professional judge sends none.
    assert f"/{JUDGE_MODEL}?web_search=false&max_tokens=4096&q=($item.grader_prompt)!''" in (
        rendered
    )
    # Bounded fresh-sample retries ride the source annotation.
    assert ";retry=2" in rendered
    # No temperature pin anywhere in the judge call (provider default, per the
    # official ResponsesSampler reasoning branch).
    assert "temperature" not in rendered


def test_the_candidate_is_invoked_without_retrieval() -> None:
    rendered = _url4(HEALTHBENCH_WORST30)
    assert "/benchmarks/candidate?web_search=false" in rendered


def test_case_selection_limits_slice_the_worst30() -> None:
    limited = HEALTHBENCH_WORST30.resource(3)
    assert limited["case_count"] == 157
    assert "slice=0:3" in _url4(HEALTHBENCH_WORST30, 3)
