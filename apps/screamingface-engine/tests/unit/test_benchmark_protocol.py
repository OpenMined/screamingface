"""The shared Benchmark protocol owns the outer Case-to-Aggregation lifecycle."""

from __future__ import annotations

import hashlib
import json

import pytest

from screamingface_engine.benchmarks.builtins import BUILTIN_BENCHMARKS
from screamingface_engine.benchmarks.case_execution import (
    CASE_EXECUTION_SCHEMA,
    install_case_execution,
)
from screamingface_engine.benchmarks.contract import encode_candidate_invocation
from screamingface_engine.benchmarks.definition import Benchmark
from screamingface_engine.benchmarks.draco.definition import DRACO, JUDGE_MODEL
from screamingface_engine.benchmarks.healthbench.definition import HEALTHBENCH_WORST30
from screamingface_engine.benchmarks.ifeval.definition import IFEVAL
from screamingface_engine.benchmarks.protocol import (
    build_evaluation_protocol,
    preserve_candidate_outcome,
)
from url4 import RelExpr, Text, render, src
from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node


def test_public_catalogue_contains_exactly_the_four_product_benchmarks() -> None:
    # OME-903 added the professional board beside the worst-30% challenge; both are
    # complete, independently meaningful benchmark identities over one baked answer key.
    assert tuple(benchmark.id for benchmark in BUILTIN_BENCHMARKS) == (
        "draco",
        "healthbench-professional",
        "healthbench-worst30",
        "ifeval",
    )


def test_canonical_draco_limit_changes_cases_only_not_grading_strength() -> None:
    full = render(DRACO.build(DRACO.case_count))
    one_case = render(DRACO.build(1))

    assert DRACO.id == "draco"
    assert DRACO.case_count == 100
    assert full.count("/" + JUDGE_MODEL) == 5
    assert one_case.count("/" + JUDGE_MODEL) == 5
    assert "iteration.slice=0:1" not in full
    # Exactly one slice is the outer Case selection; criteria remain unsliced.
    assert one_case.count("iteration.slice=0:1") == 1


def test_canonical_draco_judge_passes_have_stable_independent_cache_slots() -> None:
    expression = render(DRACO.build(1))

    assert expression.count("web_search=false") == 5
    for seed in range(1, 6):
        assert expression.count(f"&seed={seed}") == 1


@pytest.mark.asyncio
async def test_protocol_preserves_selected_order_and_collects_a_case_failure() -> None:
    node = Url4Node("benchmark-protocol")
    node.data(
        "/example/cases",
        json.dumps(
            [
                {"id": 11, "input": "first"},
                {"id": 22, "input": "second"},
                {"id": 33, "input": "unselected"},
            ]
        ),
        media_type="application/json",
    )

    @node.endpoint("/example/evaluate-case")
    def evaluate_case(request: Request) -> str:
        if request.intent == "22":
            raise ResolutionError("candidate failed", code="candidate_failed", permanent=True)
        return json.dumps({"case_id": int(request.intent), "output": request.context})

    @node.endpoint("/example/aggregate")
    def aggregate(request: Request) -> str:
        return json.dumps(
            {
                "intent": request.intent,
                "case_evaluations": json.loads(request.context),
            }
        )

    protocol = build_evaluation_protocol(
        cases_route="/example/cases",
        case_evaluation=RelExpr(
            path="/example/evaluate-case",
            context="$item.input",
            intent=Text("$item.id"),
        ),
        selected_case_count=2,
        available_case_count=3,
        aggregate_route="/example/aggregate",
    )

    result = json.loads((await node.evaluate(render(protocol))).text)

    assert result == {
        "intent": "aggregate:2",
        "case_evaluations": [
            {"case_id": 11, "output": "first"},
            {"error": {"kind": "ResolutionError", "message": "candidate failed"}},
        ],
    }


@pytest.mark.asyncio
async def test_case_execution_preserves_candidate_invocation_when_grading_fails() -> None:
    node = Url4Node("benchmark-case-execution")

    @node.endpoint("/candidate")
    def candidate(_request: Request) -> str:
        return encode_candidate_invocation("", "content_filter", "exact refusal")

    @node.endpoint("/grade")
    def grade(_request: Request) -> str:
        raise ResolutionError("checker unavailable", code="checker_failed", permanent=True)

    install_case_execution(node)

    protected = preserve_candidate_outcome(
        candidate_invocation=RelExpr(path="/candidate", context="question", intent=Text("")),
        grading=RelExpr(
            path="/grade",
            context="$candidate_invocation",
            intent=Text(""),
        ),
        case_id="case-1",
    )

    result = json.loads((await node.evaluate(render(protected))).text)

    assert result == {
        "schema": CASE_EXECUTION_SCHEMA,
        "case_id": "case-1",
        "candidate_invocation": encode_candidate_invocation("", "content_filter", "exact refusal"),
        "grading": [{"error": {"kind": "ResolutionError", "message": "checker unavailable"}}],
    }


def test_protocol_rejects_an_impossible_case_selection() -> None:
    with pytest.raises(ValueError, match="selected_case_count"):
        build_evaluation_protocol(
            cases_route="/example/cases",
            case_evaluation=RelExpr(path="/example/evaluate-case"),
            selected_case_count=4,
            available_case_count=3,
            aggregate_route="/example/aggregate",
        )


@pytest.mark.parametrize(
    ("benchmark", "expected_sha256"),
    (
        (DRACO, "6a9e0deb13a9e88868dc5452cce46527f89236be2aa34da3fbaa7afb413ecefa"),
        (IFEVAL, "c01431240e88cbe76fcbebfa3cab9fb36f36f70e8fa28807a070bbe5fb3f21eb"),
        (
            HEALTHBENCH_WORST30,
            "a5a729e1fcc53c7bb4c506f8a29a577ad4c68e983dcc32c6a9edcd33a443054c",
        ),
    ),
)
def test_canonical_benchmark_url4_is_pinned_byte_for_byte(
    benchmark: Benchmark, expected_sha256: str
) -> None:
    url4 = render(benchmark.build(benchmark.case_count))

    assert hashlib.sha256(url4.encode()).hexdigest() == expected_sha256


def test_canonical_ifeval_binds_the_exact_selected_count_for_aggregation() -> None:
    assert "!'aggregate:2'" in render(IFEVAL.build(2))


@pytest.mark.asyncio
async def test_protocol_resolves_shared_bindings_before_case_iteration() -> None:
    node = Url4Node("benchmark-bindings")
    node.data(
        "/example/cases",
        json.dumps([{"id": 1, "input": "case"}]),
        media_type="application/json",
    )

    @node.endpoint("/example/evaluate-case")
    def evaluate_case(request: Request) -> str:
        return request.context

    @node.endpoint("/example/aggregate")
    def aggregate(request: Request) -> str:
        return request.context

    protocol = build_evaluation_protocol(
        cases_route="/example/cases",
        case_evaluation=RelExpr(
            path="/example/evaluate-case", context="$shared", intent=Text("$item.id")
        ),
        selected_case_count=1,
        available_case_count=1,
        aggregate_route="/example/aggregate",
        bindings=(src(Text("resolved-once"), name="shared", weight=0.0),),
    )

    assert json.loads((await node.evaluate(render(protocol))).text) == ["resolved-once"]
