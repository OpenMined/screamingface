"""Benchmark-owned runtime installation and wide-payload execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import BENCHMARKS, install_benchmarks
from url4_cloud.benchmarks.contract import encode_candidate_invocation
from url4_cloud.benchmarks.draco.case_evaluation import (
    bind_case_evaluation,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.definition import (
    AGGREGATE_ROUTE,
    CASES_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA
from url4_cloud.benchmarks.ifeval.definition import (
    CASES_ROUTE as IFEVAL_CASES_ROUTE,
)
from url4_cloud.benchmarks.ifeval.definition import (
    CHECK_ROUTE as IFEVAL_CHECK_ROUTE,
)


def _assets(root: Path) -> None:
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text('[{"id":1,"input":"Question"}]', encoding="utf-8")
    (root / "criteria" / "1.json").write_text(
        '[{"id":"c1","requirement":"Correct","criterion_type":"positive"}]',
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(
        json.dumps({"sections": [{"id": "correctness", "criteria": [{"id": "c1", "weight": 1}]}]}),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_registry_installs_all_versioned_draco_routes(tmp_path: Path) -> None:
    _assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    assert {TASKS_ROUTE, VERDICT_ROUTE, AGGREGATE_ROUTE} <= set(node.processor_routes())
    assert json.loads(await node.fetch(CASES_ROUTE, relative=True))[0]["input"] == "Question"
    # WHY per-registry prefixes: the original draco-only assertion was structurally
    # incompatible with a second installed runtime (surfaced + relaxed in OME-719).
    prefixes = tuple(f"/benchmarks/{benchmark_id}/" for benchmark_id in BENCHMARKS)
    assert all(route.startswith(prefixes) for route in node.processor_routes())


def _ifeval_assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Write one sentence without commas."},'
        '{"id":2,"input":"Write at least 50 words without commas."}]',
        encoding="utf-8",
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1000,
                "prompt": "Write one sentence without commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )
    (root / "instructions" / "2.json").write_text(
        json.dumps(
            {
                "key": 1001,
                "prompt": "Write at least 50 words without commas.",
                "instruction_id_list": [
                    "punctuation:no_comma",
                    "length_constraints:number_words",
                ],
                "kwargs": [{}, {"relation": "at least", "num_words": 50}],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_ifeval_check_route_grades_a_response(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    record = await _ifeval_check(
        node,
        encode_candidate_invocation("A sentence with no comma at all.", "stop"),
        "1",
    )

    assert record["schema"] == "screamingface.ifeval-check.v1"
    assert record["case_id"] == 1
    assert record["valid"] is True
    assert record["strict"] == [True]
    assert record["loose"] == [True]


@pytest.mark.asyncio
async def test_ifeval_check_intent_carries_an_optional_attempt(tmp_path: Path) -> None:
    # AIDEV-NOTE: raw commas in a literal url4 context act as group separators — the
    # real chain passes REFERENCES ($prior_N) resolved after parsing, so this test
    # violates the word-count constraint with comma-free text instead.
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    record = await _ifeval_check(
        node,
        encode_candidate_invocation("A short comma-free answer.", "length"),
        "2:2",
    )

    assert record["case_id"] == 2
    assert record["attempt"] == 2
    assert record["strict"] == [True, False]
    # The retry path needs the checker's own wording of what failed.
    assert record["violations"]
    assert "50" in record["violations"][0]


async def _ifeval_check(node: Url4Node, invocation: str, intent: str) -> dict[str, Any]:
    """Exercise the check route through the same value binding the Benchmark uses.

    Candidate Invocation JSON is runtime data. Embedding it directly as expression source text
    asks URL4 to parse its braces as structure and is not equivalent to ``$candidate_result``.
    """

    expression = expr(
        src(Text(invocation), name="candidate_result", weight=0.0),
        src(
            RelExpr(
                path=IFEVAL_CHECK_ROUTE,
                context="$candidate_result",
                intent=Text(intent),
            ),
            name="record",
            weight=0.0,
        ),
        intent=Text("$record"),
    )
    return json.loads((await node.evaluate(render(expression))).text)


@pytest.mark.asyncio
async def test_ifeval_check_rejects_a_malformed_attempt(tmp_path: Path) -> None:
    _ifeval_assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    with pytest.raises(ResolutionError) as caught:
        await node.evaluate(
            render(
                RelExpr(
                    path=IFEVAL_CHECK_ROUTE,
                    context="anything",
                    intent=Text("1:zero"),
                )
            )
        )

    assert caught.value.code == "benchmark_unavailable"


@pytest.mark.asyncio
async def test_ifeval_check_without_assets_is_unavailable_not_missing_route(
    tmp_path: Path,
) -> None:
    node = Url4Node("test")
    install_benchmarks(node, tmp_path / "missing")

    with pytest.raises(ResolutionError) as caught:
        await node.fetch(IFEVAL_CASES_ROUTE, relative=True)

    assert caught.value.code == "benchmark_unavailable"
    assert caught.value.permanent is True


@pytest.mark.asyncio
async def test_missing_assets_fail_as_unavailable_not_missing_route(tmp_path: Path) -> None:
    node = Url4Node("test")
    install_benchmarks(node, tmp_path / "missing")

    with pytest.raises(ResolutionError) as caught:
        await node.fetch(CASES_ROUTE, relative=True)

    assert caught.value.code == "benchmark_unavailable"
    assert caught.value.permanent is True


@pytest.mark.asyncio
async def test_aggregate_accepts_payload_larger_than_process_argv(tmp_path: Path) -> None:
    """The row collection stays in-process even when it exceeds common ARG_MAX limits."""

    _assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    case = {
        "schema": CASE_SCHEMA,
        "case_id": 1,
        "input": "Question",
        "output": "Answer",
        "finish_reason": "stop",
        "metadata": {},
    }
    check = {
        "schema": CHECK_SCHEMA,
        "case_id": 1,
        "criterion_id": "c1",
        "criterion_type": "positive",
        "requirement": "Correct",
    }
    evidence = {
        "schema": "screamingface.criterion-verdict.v1",
        "case_id": 1,
        "criterion_id": "c1",
        "sequence": 1,
        "producer_type": "model",
        "producer_id": "fixture-judge",
        "valid": True,
        "explanation": "x" * 2_100_000,
        "criterion_status": "MET",
        "raw_output": '{"criterion_status":"MET"}',
    }
    criterion = bind_criterion_evaluation(1, case, check, [evidence])
    row = json.dumps(
        bind_case_evaluation(1, [criterion]),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    expression = render(
        RelExpr(
            path=AGGREGATE_ROUTE,
            context=json.dumps([row]),
            intent=Text("aggregate"),
        )
    )

    result = json.loads((await node.evaluate(expression)).text)

    assert result["score"] == 1.0
    assert result["case_count"] == 1


@pytest.mark.asyncio
async def test_aggregate_refuses_to_report_success_when_no_cases_scored(tmp_path: Path) -> None:
    """INVARIANT: no Case result is an Evaluation failure, never a Candidate score of zero."""

    _assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    expression = render(
        RelExpr(
            path=AGGREGATE_ROUTE,
            context="[]",
            intent=Text("aggregate"),
        )
    )

    with pytest.raises(ResolutionError, match="no DRACO rows") as caught:
        await node.evaluate(expression)

    assert caught.value.code == "benchmark_unavailable"
    assert caught.value.permanent is True
