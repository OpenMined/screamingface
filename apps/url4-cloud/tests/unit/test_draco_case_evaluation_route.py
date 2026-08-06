"""DRACO emits one exact Case Evaluation before benchmark Aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.draco.case_evaluation import CASE_EVALUATION_SCHEMA
from url4_cloud.benchmarks.draco.definition import (
    CASE_EVALUATION_ROUTE,
    CRITERION_EVALUATION_ROUTE,
    DRACO,
    DRACO_LITE,
    DRACO_SMOKE,
    LITE_CASE_EVALUATION_ROUTE,
    LITE_CRITERION_EVALUATION_ROUTE,
    SMOKE_CASE_EVALUATION_ROUTE,
    SMOKE_CRITERION_EVALUATION_ROUTE,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA
from url4_cloud.benchmarks.draco.runtime import install
from url4_cloud.benchmarks.draco.verdict import SCHEMA as VERDICT_SCHEMA


async def _call(node: Url4Node, path: str, context: object, intent: str) -> object:
    expression = expr(
        src(Text(json.dumps(context)), name="payload", weight=0.0),
        src(
            RelExpr(path=path, context="$payload", intent=Text(intent)),
            name="result",
            weight=0.0,
        ),
        intent=Text("$result"),
    )
    return json.loads((await node.evaluate(render(expression))).text)


def test_every_draco_resource_builds_exact_criterion_and_case_evaluations() -> None:
    profiles = (
        (DRACO, CRITERION_EVALUATION_ROUTE, CASE_EVALUATION_ROUTE),
        (DRACO_LITE, LITE_CRITERION_EVALUATION_ROUTE, LITE_CASE_EVALUATION_ROUTE),
        (DRACO_SMOKE, SMOKE_CRITERION_EVALUATION_ROUTE, SMOKE_CASE_EVALUATION_ROUTE),
    )

    for benchmark, criterion_route, case_route in profiles:
        url4 = benchmark.resource(1)["url4"]
        assert isinstance(url4, str)
        assert url4.count(criterion_route) == 1
        assert url4.count(case_route) == 1


@pytest.mark.asyncio
async def test_runtime_packs_one_criterion_then_one_case_evaluation(tmp_path: Path) -> None:
    node = Url4Node("test")
    install(node, tmp_path)
    case = {
        "schema": CASE_SCHEMA,
        "case_id": 1,
        "input": "Question 1",
        "output": "Answer 1",
        "finish_reason": "stop",
        "metadata": {},
    }
    check = {
        "schema": CHECK_SCHEMA,
        "case_id": 1,
        "criterion_id": "c1",
        "criterion_type": "positive",
        "requirement": "Be correct",
    }
    verdict = {
        "schema": VERDICT_SCHEMA,
        "case_id": 1,
        "criterion_id": "c1",
        "sequence": 1,
        "producer_type": "model",
        "producer_id": "fixture-judge",
        "valid": True,
        "explanation": "The requirement is met.",
        "criterion_status": "MET",
        "raw_output": '{"criterion_status":"MET"}',
    }
    criterion = await _call(
        node,
        SMOKE_CRITERION_EVALUATION_ROUTE,
        {
            "case": json.dumps(case),
            "check": json.dumps(check),
            "evidence_1": json.dumps(verdict),
        },
        "1",
    )

    result = await _call(node, SMOKE_CASE_EVALUATION_ROUTE, [criterion], "1")

    assert result == {
        "schema": CASE_EVALUATION_SCHEMA,
        "case": case,
        "checks": [check],
        "evidence": [verdict],
    }
