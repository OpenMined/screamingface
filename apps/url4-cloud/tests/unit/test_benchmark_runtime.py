"""Benchmark-owned runtime installation and wide-payload execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, render
from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.draco.definition import (
    AGGREGATE_ROUTE,
    CASES_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
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
    assert all(route.startswith("/benchmarks/draco/") for route in node.processor_routes())


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
    verdict = {
        "schema": "screamingface.criterion-verdict.v1",
        "criterion_id": "c1",
        "valid": True,
        "explanation": "x" * 2_100_000,
        "criterion_status": "MET",
    }
    expression = render(
        RelExpr(
            path=AGGREGATE_ROUTE,
            context=json.dumps([json.dumps(verdict)]),
            intent=Text("aggregate"),
        )
    )

    result = json.loads((await node.evaluate(expression)).text)

    assert result["score"] == 1.0
    assert result["case_count"] == 1
