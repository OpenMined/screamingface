"""The shared Benchmark protocol owns the outer Case-to-Aggregation lifecycle."""

from __future__ import annotations

import hashlib
import json

import pytest

from url4 import RelExpr, Text, render, src
from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.builtins import BUILTIN_BENCHMARKS
from url4_cloud.benchmarks.definition import Benchmark
from url4_cloud.benchmarks.draco.definition import DRACO, JUDGE_MODEL
from url4_cloud.benchmarks.healthbench.definition import HEALTHBENCH_WORST30
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.protocol import build_evaluation_protocol


def test_public_catalogue_contains_exactly_the_three_product_benchmarks() -> None:
    assert tuple(benchmark.id for benchmark in BUILTIN_BENCHMARKS) == (
        "draco",
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
        (DRACO, "559bbcacbf7da44ccc811e205ab2c20ceb232f1ba126922f7d053741b3bd3de0"),
        (IFEVAL, "f8be102aafa71f04939f6d8751b0c8fc20a694a233caea7317176f1827bbed41"),
        (
            HEALTHBENCH_WORST30,
            "f89d92e3efce7f9f08ad7cef5db16bbbbb68be2d05c5e17a7914a159eba866b9",
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
