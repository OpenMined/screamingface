"""The safe DRACO smoke protocol is structurally faithful and explicitly non-canonical.

FEATURE: OME-712 — notebooks can validate the DRACO execution path without accidentally
launching the full paid Benchmark.
STORY: as a researcher, I can test Model and Fusion plumbing cheaply without mistaking the
diagnostic score for a publishable DRACO result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4 import RelExpr, Text, render
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import ASSETS_ENV, BENCHMARKS, install_benchmarks
from url4_cloud.benchmarks.draco.definition import (
    DRACO,
    DRACO_SMOKE,
    JUDGE_MODEL,
    SMOKE_AGGREGATE_ROUTE,
    SMOKE_CASES_ROUTE,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA
from url4_cloud.rest.benchmarks import router


def test_smoke_is_a_separate_noncanonical_benchmark() -> None:
    assert BENCHMARKS["draco/smoke"] is DRACO_SMOKE
    assert DRACO_SMOKE.id == "draco/smoke"
    assert DRACO_SMOKE.variant == "smoke"
    assert DRACO_SMOKE.case_count == 1
    assert DRACO_SMOKE.revision != DRACO.revision
    assert "not comparable" in DRACO_SMOKE.description.lower()


def test_smoke_reduces_only_protocol_multiplicity() -> None:
    # INVARIANT: both expressions cross the same Candidate/retrieval/verdict/reducer seams.
    canonical = render(DRACO.build(1))
    smoke = render(DRACO_SMOKE.build(1))

    for route_fragment in ("/candidate", "/tasks", "/criterion-verdict", "/aggregate"):
        assert route_fragment in canonical
        assert route_fragment in smoke

    judge_route = "/" + JUDGE_MODEL
    assert canonical.count(judge_route) == 5
    assert smoke.count(judge_route) == 1

    # Canonical-one slices Cases only; smoke additionally slices the criterion collection.
    assert canonical.count("iteration.slice=0:1") == 1
    assert smoke.count("iteration.slice=0:1") == 2


def test_canonical_draco_contract_is_unchanged() -> None:
    assert DRACO.id == "draco"
    assert DRACO.variant == "canonical"
    assert DRACO.case_count == 100
    assert render(DRACO.build(100)).count("/" + JUDGE_MODEL) == 5
    assert "iteration.slice=0:1" not in render(DRACO.build(100))


def _two_case_assets(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "cases.json").write_text(
        json.dumps(
            [
                {"id": 1, "input": "First question", "domain": "Academic"},
                {"id": 2, "input": "Second question", "domain": "Finance"},
            ]
        ),
        encoding="utf-8",
    )


def test_smoke_public_cases_expose_only_the_pinned_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_case_assets(tmp_path / "draco")
    monkeypatch.setenv(ASSETS_ENV, str(tmp_path))
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/v1/benchmarks/draco/smoke/cases")

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 1
    assert page["data"] == [{"id": 1, "input": "First question"}]


@pytest.mark.asyncio
async def test_smoke_private_cases_expose_only_the_pinned_case(tmp_path: Path) -> None:
    _two_case_assets(tmp_path / "draco")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    cases = json.loads(await node.fetch(SMOKE_CASES_ROUTE, relative=True))

    assert [case["id"] for case in cases] == [1]


@pytest.mark.asyncio
async def test_smoke_runtime_reports_its_own_identity_and_one_judge_pass(tmp_path: Path) -> None:
    root = tmp_path / "draco"
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text('[{"id":1,"input":"Question"}]', encoding="utf-8")
    (root / "criteria" / "1.json").write_text(
        '[{"id":"c1","requirement":"Correct","criterion_type":"positive"},'
        '{"id":"c2","requirement":"Complete","criterion_type":"positive"}]',
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(
        '{"sections":[{"id":"correctness","criteria":['
        '{"id":"c1","weight":1},{"id":"c2","weight":1}]}]}',
        encoding="utf-8",
    )
    raw_output = json.dumps({"explanation": "evidence", "criterion_status": "MET"})
    row = "\n".join(
        map(
            json.dumps,
            (
                {
                    "schema": CASE_SCHEMA,
                    "case_id": 1,
                    "input": "Question",
                    "output": "Answer",
                    "finish_reason": "stop",
                    "metadata": {},
                },
                {
                    "schema": CHECK_SCHEMA,
                    "case_id": 1,
                    "criterion_id": "c1",
                    "criterion_type": "positive",
                    "requirement": "Correct",
                },
                {
                    "schema": "screamingface.criterion-verdict.v1",
                    "case_id": 1,
                    "criterion_id": "c1",
                    "sequence": 1,
                    "producer_type": "model",
                    "producer_id": "fixture-judge",
                    "valid": True,
                    "explanation": "evidence",
                    "criterion_status": "MET",
                    "raw_output": raw_output,
                },
            ),
        )
    )
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)

    result = json.loads(
        (
            await node.evaluate(
                render(
                    RelExpr(
                        path=SMOKE_AGGREGATE_ROUTE,
                        context=json.dumps([row]),
                        intent=Text("aggregate"),
                    )
                )
            )
        ).text
    )

    assert result["benchmark_id"] == DRACO_SMOKE.id
    assert result["benchmark_revision"] == DRACO_SMOKE.revision
    assert result["metrics"]["n_runs"] == 1
    assert result["metrics"]["coverage"] == 1.0
    assert result["metrics"]["verdicts_expected"] == 1
