"""The IFEval runtime emits one exact per-Case evaluation envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.contract import encode_candidate_invocation
from url4_cloud.benchmarks.ifeval.case_evaluation import CASE_EVALUATION_SCHEMA, CHECK_SCHEMA
from url4_cloud.benchmarks.ifeval.definition import (
    CASE_EVALUATION_ROUTE,
    CHECK_ROUTE,
    IFEVAL,
    ROUTE_PREFIX,
)
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_LANL_ENSEMBLE,
    IFEVAL_SELF_CORRECTIVE,
)
from url4_cloud.benchmarks.ifeval.runtime import install


def _assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Describe tea without commas."}]', encoding="utf-8"
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1,
                "prompt": "Describe tea without commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_runtime_packs_ordered_attempts_into_one_case_evaluation(tmp_path: Path) -> None:
    node = Url4Node("test")
    install(node, tmp_path)
    record = {
        "schema": CHECK_SCHEMA,
        "case_id": 1,
        "attempt": 1,
        "valid": True,
        "answer": "A compliant answer",
        "refusal": None,
        "finish_reason": "stop",
        "instruction_id_list": ["punctuation:no_comma"],
        "descriptions": ["Do not use commas."],
        "strict": [True],
        "loose": [True],
        "violations": [],
    }
    payload = json.dumps({"attempt_1": json.dumps(record)})
    expression = expr(
        src(Text(payload), name="payload", weight=0.0),
        src(
            RelExpr(
                path=f"{ROUTE_PREFIX}/case-evaluation",
                context="$payload",
                intent=Text("1"),
            ),
            name="case_evaluation",
            weight=0.0,
        ),
        intent=Text("$case_evaluation"),
    )

    result = json.loads((await node.evaluate(render(expression))).text)

    assert result == {
        "schema": CASE_EVALUATION_SCHEMA,
        "case_id": 1,
        "attempts": [record],
    }


@pytest.mark.asyncio
async def test_runtime_grades_exact_refusal_text_through_the_normal_checker(
    tmp_path: Path,
) -> None:
    _assets(tmp_path)
    node = Url4Node("test")
    install(node, tmp_path)
    exact = "I cannot comply."
    expression = expr(
        src(
            Text(encode_candidate_invocation("", "content_filter", exact)),
            name="candidate_result",
            weight=0.0,
        ),
        src(
            RelExpr(path=CHECK_ROUTE, context="$candidate_result", intent=Text("1:1")),
            name="record",
            weight=0.0,
        ),
        intent=Text("$record"),
    )

    record = json.loads((await node.evaluate(render(expression))).text)

    assert record["answer"] == exact
    assert record["refusal"] == exact
    assert record["finish_reason"] == "content_filter"
    assert record["strict"] == [True]


def test_canonical_resource_packs_the_check_before_aggregation() -> None:
    url4 = IFEVAL.resource(1)["url4"]

    assert isinstance(url4, str)
    assert url4.count(CASE_EVALUATION_ROUTE) == 1


def test_self_corrective_resource_packs_attempts_before_aggregation() -> None:
    url4 = IFEVAL_SELF_CORRECTIVE.resource(1)["url4"]

    assert isinstance(url4, str)
    assert url4.count(CASE_EVALUATION_ROUTE) == 1


def test_lanl_ensemble_resource_packs_attempts_before_aggregation() -> None:
    from url4_cloud.benchmarks.ifeval.corrective_policy import LANL_ENVELOPE_ROUTE

    url4 = IFEVAL_LANL_ENSEMBLE.resource(1)["url4"]

    assert isinstance(url4, str)
    # The lanl-ensemble packs its gated attempt chain via its own envelope route.
    assert url4.count(LANL_ENVELOPE_ROUTE) == 1
