"""Public flat Benchmark resources exposed by the ScreamingFace Engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4 import build, render
from url4_cloud.benchmarks import ASSETS_ENV, BENCHMARKS
from url4_cloud.benchmarks.ifeval.iterative_correction import IFEVAL_SELF_CORRECTIVE
from url4_cloud.rest.benchmarks import router

pytestmark = pytest.mark.anyio


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_slash_qualified_id_returns_one_flat_executable_benchmark(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/ifeval/self-corrective", params={"limit": 1})

    assert response.status_code == 200
    resource = response.json()
    assert set(resource) == {
        "schema",
        "id",
        "variant",
        "title",
        "description",
        "revision",
        "case_count",
        "url4",
    }
    assert resource["schema"] == "screamingface.benchmark.v1"
    assert resource["id"] == "ifeval/self-corrective"
    assert resource["variant"] == "self-corrective"
    assert resource["case_count"] == 541
    assert render(build(resource["url4"])) == resource["url4"]
    assert "iteration.slice=0:1" in resource["url4"]


def test_catalog_lists_every_executable_benchmark_as_one_flat_entry(client: TestClient) -> None:
    response = client.get("/v1/benchmarks")

    assert response.status_code == 200
    catalog = response.json()
    assert catalog["object"] == "list"
    assert catalog["default"] == "draco"
    assert {entry["id"] for entry in catalog["data"]} == {
        "draco",
        "draco/lite",
        "draco/smoke",
        "healthbench/smoke",
        "healthbench/worst30",
        "ifeval",
        "ifeval/self-corrective",
        "ifeval/verifying-ensemble",
    }
    for entry in catalog["data"]:
        benchmark = BENCHMARKS[entry["id"]]
        assert entry == {
            "object": "benchmark",
            "id": benchmark.id,
            "variant": benchmark.variant,
            "title": benchmark.title,
            "description": benchmark.description,
            "href": f"/v1/benchmarks/{benchmark.id}",
        }


def test_slash_qualified_case_route_uses_shared_assets_and_selected_revision(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assets = tmp_path / "ifeval"
    assets.mkdir()
    (assets / "cases.json").write_text(
        json.dumps([{"id": 1, "input": "Describe tea without commas."}]),
        encoding="utf-8",
    )
    monkeypatch.setenv(ASSETS_ENV, str(tmp_path))

    response = client.get("/v1/benchmarks/ifeval/self-corrective/cases")

    assert response.status_code == 200
    page = response.json()
    assert page["benchmark"] == "ifeval/self-corrective"
    assert page["revision"] == IFEVAL_SELF_CORRECTIVE.revision
    assert page["data"] == [{"id": 1, "input": "Describe tea without commas."}]
