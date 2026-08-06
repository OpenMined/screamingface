"""DRACO lite is a bounded directional preview, not a smaller canonical score.

FEATURE: OME-712 — researchers can compare Candidate plumbing and directional quality without
paying for the complete 100-Case, five-pass Benchmark.
STORY: as a researcher, I can run every rubric criterion over a pinned, reviewable Case subset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4 import RelExpr, Text, expr, render, src
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import ASSETS_ENV, BENCHMARKS, install_benchmarks
from url4_cloud.benchmarks.contract import encode_candidate_invocation
from url4_cloud.benchmarks.draco.case_evaluation import (
    bind_case_evaluation,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.definition import (
    DRACO,
    DRACO_LITE,
    DRACO_SMOKE,
    JUDGE_MODEL,
    LITE_AGGREGATE_ROUTE,
    LITE_CASE_IDS,
    LITE_CASES_ROUTE,
    LITE_CRITERION_COUNT,
    LITE_CRITERION_SELECTION,
    LITE_TASKS_ROUTE,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA
from url4_cloud.rest.benchmarks import router

_EXPECTED_IDS = (2, 15)


def _assets(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "criteria").mkdir()
    (root / "rubrics").mkdir()
    cases = []
    for case_id in range(1, 101):
        cases.append({"id": case_id, "input": f"Question {case_id}", "domain": "test"})
        criteria = [
            {
                "id": f"c{index}",
                "requirement": f"Correct {index}",
                "criterion_type": "positive",
            }
            for index in range(1, 13)
        ]
        (root / "criteria" / f"{case_id}.json").write_text(
            json.dumps(criteria),
            encoding="utf-8",
        )
        rubric_criteria = [
            {"id": f"c{index}", "requirement": f"Correct {index}", "weight": 1}
            for index in range(1, 13)
        ]
        (root / "rubrics" / f"{case_id}.json").write_text(
            json.dumps({"sections": [{"id": "correctness", "criteria": rubric_criteria}]}),
            encoding="utf-8",
        )
    (root / "cases.json").write_text(json.dumps(cases), encoding="utf-8")


def test_lite_is_a_separate_noncanonical_benchmark() -> None:
    assert BENCHMARKS["draco/lite"] is DRACO_LITE
    assert DRACO_LITE.id == "draco/lite"
    assert DRACO_LITE.variant == "lite"
    assert DRACO_LITE.case_count == 2
    assert DRACO_LITE.case_ids == _EXPECTED_IDS == LITE_CASE_IDS
    assert DRACO_LITE.revision not in {DRACO.revision, DRACO_SMOKE.revision}
    assert "not comparable" in DRACO_LITE.description.lower()
    assert LITE_CRITERION_SELECTION == "axis-balanced"
    assert "axis-balanced" in DRACO_LITE.description.lower()


def test_lite_caps_criteria_and_reduces_judge_repetition() -> None:
    expression = render(DRACO_LITE.build(DRACO_LITE.case_count))

    for route_fragment in ("/candidate", "/tasks", "/criterion-verdict", "/aggregate"):
        assert route_fragment in expression
    assert expression.count("/" + JUDGE_MODEL) == 1
    assert f"iteration.slice=0:{LITE_CRITERION_COUNT}" in expression


def test_lite_public_cases_expose_the_ordered_pinned_subset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _assets(tmp_path / "draco")
    monkeypatch.setenv(ASSETS_ENV, str(tmp_path))
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/v1/benchmarks/draco/lite/cases")

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    assert [case["id"] for case in page["data"]] == list(_EXPECTED_IDS)


@pytest.mark.asyncio
async def test_lite_private_cases_expose_the_ordered_pinned_subset(tmp_path: Path) -> None:
    _assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    cases = json.loads(await node.fetch(LITE_CASES_ROUTE, relative=True))

    assert [case["id"] for case in cases] == list(_EXPECTED_IDS)


@pytest.mark.asyncio
async def test_lite_task_route_selects_criteria_across_axes(tmp_path: Path) -> None:
    root = tmp_path / "draco"
    _assets(root)
    rubric = {
        "sections": [
            {
                "id": axis,
                "criteria": [
                    {"id": f"{axis}{index}", "requirement": "Correct", "weight": 1}
                    for index in range(1, 4)
                ],
            }
            for axis in ("a", "b", "c", "d")
        ]
    }
    criteria = [
        {
            "id": criterion["id"],
            "requirement": criterion["requirement"],
            "criterion_type": "positive",
        }
        for section in rubric["sections"]
        for criterion in section["criteria"]
    ]
    (root / "rubrics" / "2.json").write_text(json.dumps(rubric), encoding="utf-8")
    (root / "criteria" / "2.json").write_text(json.dumps(criteria), encoding="utf-8")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    expression = expr(
        src(
            Text(encode_candidate_invocation("Answer", "stop")),
            name="candidate_result",
            weight=0.0,
        ),
        src(
            RelExpr(
                path=LITE_TASKS_ROUTE,
                context="$candidate_result",
                intent=Text("2"),
            ),
            name="criteria",
            weight=0.0,
        ),
        intent=Text("$criteria"),
    )
    result = json.loads((await node.evaluate(render(expression))).text)

    assert [criterion["criterion_id"] for criterion in result] == [
        "a1",
        "b1",
        "c1",
        "d1",
        "a2",
        "b2",
        "c2",
        "d2",
        "a3",
        "b3",
    ]


@pytest.mark.asyncio
async def test_lite_runtime_reports_its_own_identity_and_one_judge_pass(tmp_path: Path) -> None:
    _assets(tmp_path / "draco")
    rows = []
    for case_id in _EXPECTED_IDS:
        raw_output = json.dumps({"explanation": "evidence", "criterion_status": "MET"})
        records = [
            {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "input": f"Question {case_id}",
                "output": f"Answer {case_id}",
                "finish_reason": "stop",
                "metadata": {"domain": "test"},
            },
        ]
        for index in range(1, LITE_CRITERION_COUNT + 1):
            records.extend(
                (
                    {
                        "schema": CHECK_SCHEMA,
                        "case_id": case_id,
                        "criterion_id": f"c{index}",
                        "criterion_type": "positive",
                        "requirement": f"Correct {index}",
                    },
                    {
                        "schema": "screamingface.criterion-verdict.v1",
                        "case_id": case_id,
                        "criterion_id": f"c{index}",
                        "sequence": 1,
                        "producer_type": "model",
                        "producer_id": "fixture-judge",
                        "valid": True,
                        "explanation": "evidence",
                        "criterion_status": "MET",
                        "raw_output": raw_output,
                    },
                )
            )
        criteria = [
            bind_criterion_evaluation(
                case_id,
                records[0] if index == 0 else None,
                records[1 + index * 2],
                [records[2 + index * 2]],
            )
            for index in range(LITE_CRITERION_COUNT)
        ]
        rows.append(bind_case_evaluation(case_id, criteria))
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    result = json.loads(
        (
            await node.evaluate(
                render(
                    expr(
                        src(Text(json.dumps(rows)), name="rows", weight=0.0),
                        src(
                            RelExpr(
                                path=LITE_AGGREGATE_ROUTE,
                                context="$rows",
                                intent=Text("aggregate"),
                            ),
                            name="result",
                            weight=0.0,
                        ),
                        intent=Text("$result"),
                    )
                )
            )
        ).text
    )

    assert result["benchmark_id"] == DRACO_LITE.id
    assert result["benchmark_revision"] == DRACO_LITE.revision
    assert result["case_count"] == 2
    assert result["metrics"]["n_runs"] == 1
    assert result["metrics"]["coverage"] == 1.0
