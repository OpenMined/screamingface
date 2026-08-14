"""DRACO emits one exact Case Evaluation before benchmark Aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, expr, render, src
from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.draco import assets as draco_assets
from url4_cloud.benchmarks.draco.case_evaluation import (
    CASE_EVALUATION_SCHEMA,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.definition import (
    CASE_EVALUATION_ROUTE,
    CASES_ROUTE,
    CRITERION_EVALUATION_ROUTE,
    DRACO,
    DRACO_LITE,
    DRACO_SMOKE,
    LITE_CASE_EVALUATION_ROUTE,
    LITE_CRITERION_EVALUATION_ROUTE,
    SMOKE_CASE_EVALUATION_ROUTE,
    SMOKE_CASES_ROUTE,
    SMOKE_CRITERION_EVALUATION_ROUTE,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA
from url4_cloud.benchmarks.draco.runtime import install_canonical, install_smoke
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


def _smoke_assets(root: Path) -> None:
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text('[{"id":1,"input":"Question 1"}]', encoding="utf-8")
    (root / "criteria" / "1.json").write_text(
        '[{"id":"c1","requirement":"Be correct","criterion_type":"positive"}]',
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(
        '{"sections":[{"id":"accuracy","criteria":[{"id":"c1","weight":1}]}]}',
        encoding="utf-8",
    )


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
    _smoke_assets(tmp_path)
    node = Url4Node("test")
    install_smoke(node, tmp_path)
    case = {
        "schema": CASE_SCHEMA,
        "case_id": 1,
        "input": "Question 1",
        "answer": "Answer 1",
        "output": "Answer 1",
        "finish_reason": "stop",
        "refusal": None,
        "execution": None,
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


def test_case_record_requires_explicit_execution_provenance() -> None:
    case = {
        "schema": CASE_SCHEMA,
        "case_id": 1,
        "input": "Question 1",
        "answer": "Answer 1",
        "output": "Answer 1",
        "finish_reason": "stop",
        "refusal": None,
        "metadata": {},
    }
    check = {
        "schema": CHECK_SCHEMA,
        "case_id": 1,
        "criterion_id": "c1",
        "criterion_type": "positive",
        "requirement": "Be correct",
    }
    evidence = {
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

    with pytest.raises(ValueError, match="invalid Case record"):
        bind_criterion_evaluation(1, case, check, [evidence])


def test_install_fails_atomically_when_assets_are_missing(tmp_path: Path) -> None:
    node = Url4Node("test")

    with pytest.raises(ResolutionError, match="could not read DRACO cases"):
        install_smoke(node, tmp_path)

    assert SMOKE_CASES_ROUTE not in node.processor_routes()


def test_canonical_install_rejects_a_truncated_case_set_atomically(tmp_path: Path) -> None:
    _smoke_assets(tmp_path)
    node = Url4Node("test")

    with pytest.raises(ResolutionError, match="expected 100 DRACO cases"):
        install_canonical(node, tmp_path)

    assert CASES_ROUTE not in node.processor_routes()


def test_asset_validation_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    _smoke_assets(tmp_path)
    cases = [{"id": 1, "input": "Question"}, {"id": 1, "input": "Duplicate"}]

    with pytest.raises(ValueError, match="repeats case_id 1"):
        draco_assets.validate_protocol_assets(tmp_path, cases, None, "all")


def test_asset_validation_rejects_empty_case_input(tmp_path: Path) -> None:
    _smoke_assets(tmp_path)

    with pytest.raises(ValueError, match="non-empty input"):
        draco_assets.validate_protocol_assets(tmp_path, [{"id": 1, "input": ""}], None, "all")


def test_asset_validation_rejects_an_empty_canonical_rubric(tmp_path: Path) -> None:
    _smoke_assets(tmp_path)
    (tmp_path / "criteria" / "1.json").write_text("[]", encoding="utf-8")
    (tmp_path / "rubrics" / "1.json").write_text('{"sections":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="no DRACO rubric criteria"):
        draco_assets.validate_protocol_assets(
            tmp_path,
            [{"id": 1, "input": "Question"}],
            None,
            "all",
        )
