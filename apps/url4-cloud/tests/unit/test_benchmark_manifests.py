"""The Engine-owned Benchmark catalog and expression resources."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from url4 import build, render
from url4_cloud.benchmarks import BENCHMARKS, DEFAULT_BENCHMARK_ID
from url4_cloud.benchmarks.draco.definition import REVISION, ROUTE_PREFIX
from url4_cloud.benchmarks.ifeval.definition import (
    CASE_COUNT as IFEVAL_CASE_COUNT,
)
from url4_cloud.benchmarks.ifeval.definition import (
    REVISION as IFEVAL_REVISION,
)
from url4_cloud.benchmarks.ifeval.definition import (
    ROUTE_PREFIX as IFEVAL_ROUTE_PREFIX,
)
from url4_cloud.rest.benchmarks import router

pytestmark = pytest.mark.anyio


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_every_benchmark_is_keyed_by_its_own_id() -> None:
    for key, benchmark in BENCHMARKS.items():
        assert benchmark.id == key


def test_the_registry_is_not_empty() -> None:
    assert BENCHMARKS


def test_listing_returns_stable_benchmark_links(client: TestClient) -> None:
    response = client.get("/v1/benchmarks")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["default"] == DEFAULT_BENCHMARK_ID
    by_id = {entry["id"]: entry for entry in body["data"]}
    assert set(by_id) == set(BENCHMARKS)
    for key, entry in by_id.items():
        expected: dict[str, object] = {
            "object": "benchmark",
            "id": key,
            "title": BENCHMARKS[key].title,
            "description": BENCHMARKS[key].description,
            "href": f"/v1/benchmarks/{key}",
        }
        if BENCHMARKS[key].methods:
            # The catalog is where a researcher learns a benchmark has protocol
            # variants and which one runs by default.
            expected["methods"] = list(BENCHMARKS[key].method_names())
            expected["default_method"] = BENCHMARKS[key].default_method
        assert entry == expected


def test_listing_is_publicly_cacheable_with_a_validator(client: TestClient) -> None:
    response = client.get("/v1/benchmarks")

    assert "public" in response.headers["cache-control"]
    assert response.headers["etag"].startswith('"')


def test_draco_resource_contains_one_complete_candidate_independent_url4(
    client: TestClient,
) -> None:
    response = client.get("/v1/benchmarks/draco?limit=1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body == {
        "schema": "screamingface.benchmark.v1",
        "id": "draco",
        "revision": REVISION,
        "case_count": 1,
        "total_case_count": 100,
        "required_models": ["openrouter/google/gemini-3.1-pro-preview"],
        "url4": body["url4"],
    }
    assert render(build(body["url4"])) == body["url4"]
    assert "/candidate" in body["url4"]
    assert "$item.input" in body["url4"]
    assert f"{ROUTE_PREFIX}/tasks" in body["url4"]
    assert body["url4"].count(f"{ROUTE_PREFIX}/criterion-verdict") == 5
    assert "/benchmark/tasks" not in body["url4"]
    assert "/openrouter/google/gemini-3.1-pro-preview" in body["url4"]
    assert "anthropic/claude-haiku" not in body["url4"]
    assert "protocol" not in body
    assert "plan" not in body


def test_ifeval_single_pass_method_is_a_complete_judge_free_url4(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/ifeval?limit=1&method=single_pass")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "schema": "screamingface.benchmark.v1",
        "id": "ifeval",
        "revision": IFEVAL_REVISION,
        "case_count": 1,
        "total_case_count": IFEVAL_CASE_COUNT,
        # INVARIANT: the judge-free exam declares NO model requirement — grading is code.
        "required_models": [],
        "url4": body["url4"],
        "method": "single_pass",
        "methods": ["corrective", "single_pass"],
        "default_method": "corrective",
        "actions": body["actions"],
    }
    assert set(body["actions"]) == {"check", "select", "finalize"}
    assert render(build(body["url4"])) == body["url4"]
    assert body["url4"].count("/candidate") == 1
    assert "$item.input" in body["url4"]
    assert f"{IFEVAL_ROUTE_PREFIX}/check" in body["url4"]
    assert f"{IFEVAL_ROUTE_PREFIX}/aggregate" in body["url4"]
    # No model node of any kind: the only routes are /candidate and the benchmark's own.
    assert "openrouter/" not in body["url4"]
    assert "judge" not in body["url4"]


def test_ifeval_total_case_count_is_the_full_dataset(client: TestClient) -> None:
    assert IFEVAL_CASE_COUNT == 541


def test_ifeval_default_resource_is_the_corrective_chain(client: TestClient) -> None:
    # WHY corrective by default: the LANL reproduction IS ifeval's purpose here
    # (owner decision, OME-725) — and the manifest says so via the method fields.
    response = client.get("/v1/benchmarks/ifeval?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "screamingface.benchmark.v1"
    assert body["id"] == "ifeval"
    assert body["method"] == "corrective"
    assert body["default_method"] == "corrective"
    assert body["required_models"] == []
    assert body["total_case_count"] == IFEVAL_CASE_COUNT
    assert render(build(body["url4"])) == body["url4"]
    # Three unrolled attempts: the candidate answers and is checked three times per case.
    assert body["url4"].count("/candidate") == 3
    assert body["url4"].count(f"{IFEVAL_ROUTE_PREFIX}/check") == 3
    assert "openrouter/" not in body["url4"]


def test_an_unknown_method_is_a_404_problem(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/ifeval?method=bogus")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_method_on_a_methodless_benchmark_is_a_404_problem(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/draco?method=single_pass")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_limit_selects_cases_before_the_expression_is_returned(client: TestClient) -> None:
    limited = client.get("/v1/benchmarks/draco?limit=2").json()
    complete = client.get("/v1/benchmarks/draco").json()

    assert limited["case_count"] == 2
    assert limited["total_case_count"] == 100
    assert limited["url4"] != complete["url4"]
    assert complete["case_count"] == 100


def test_default_alias_resolves_without_a_catalog_fetch(client: TestClient) -> None:
    explicit = client.get(f"/v1/benchmarks/{DEFAULT_BENCHMARK_ID}?limit=1")
    default = client.get("/v1/benchmarks/default?limit=1")

    assert default.status_code == 200
    assert default.json() == explicit.json()


def test_resource_has_a_representation_specific_strong_etag(client: TestClient) -> None:
    one = client.get("/v1/benchmarks/draco?limit=1")
    two = client.get("/v1/benchmarks/draco?limit=2")

    assert "public" in one.headers["cache-control"]
    assert one.headers["etag"].startswith('"')
    assert one.headers["etag"] != two.headers["etag"]


def test_matching_if_none_match_gets_304_with_no_body(client: TestClient) -> None:
    etag = client.get("/v1/benchmarks/draco?limit=1").headers["etag"]

    response = client.get(
        "/v1/benchmarks/draco?limit=1",
        headers={"If-None-Match": etag},
    )

    assert response.status_code == 304
    assert not response.content


def test_unknown_id_is_404_problem_json(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404


@pytest.mark.parametrize("limit", ["0", "-1", "false", "1.5"])
def test_limit_must_be_a_positive_integer(client: TestClient, limit: str) -> None:
    response = client.get("/v1/benchmarks/draco", params={"limit": limit})

    assert response.status_code == 422


def test_planning_post_route_no_longer_exists(client: TestClient) -> None:
    response = client.post("/v1/benchmarks/draco/plans", json={})

    assert response.status_code == 404


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "draco/../../secret", "%2e%2e%2f"],
)
def test_a_traversal_shaped_id_is_never_served(client: TestClient, hostile: str) -> None:
    response = client.get(f"/v1/benchmarks/{hostile}")

    assert response.status_code in (404, 400)
    assert "root:" not in response.text
