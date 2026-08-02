"""The Engine-owned Benchmark catalog and expression resources."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from url4 import build, render
from url4_cloud.benchmarks import BENCHMARKS, DEFAULT_BENCHMARK_ID
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
        assert entry == {
            "object": "benchmark",
            "id": key,
            "title": BENCHMARKS[key].title,
            "description": BENCHMARKS[key].description,
            "href": f"/v1/benchmarks/{key}",
        }


def test_listing_is_publicly_cacheable_with_a_validator(client: TestClient) -> None:
    response = client.get("/v1/benchmarks")

    assert "public" in response.headers["cache-control"]
    assert response.headers["etag"].startswith('"')


def test_draco_resource_contains_one_complete_candidate_independent_url4(
    client: TestClient,
) -> None:
    response = client.get("/v1/benchmarks/draco-lite?limit=1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body == {
        "schema": "screamingface.benchmark.v1",
        "object": "benchmark",
        "id": "draco-lite",
        "title": "DRACO Lite",
        "description": "Research-quality rubric evaluation.",
        "case_count": 1,
        "total_case_count": 100,
        "metrics": {"primary": "normalized_score", "direction": "maximize"},
        "capabilities": {
            "candidate": ["web_search", "web_fetch"],
            "runtime": [],
        },
        "required_models": ["openrouter/google/gemini-3.1-pro-preview"],
        "candidate_invocations": 1,
        "url4": body["url4"],
    }
    assert render(build(body["url4"])) == body["url4"]
    assert "/candidate" in body["url4"]
    assert "$question" in body["url4"]
    assert "/openrouter/google/gemini-3.1-pro-preview" in body["url4"]
    assert "anthropic/claude-haiku" not in body["url4"]
    assert "protocol" not in body
    assert "plan" not in body


def test_limit_selects_cases_before_the_expression_is_returned(client: TestClient) -> None:
    limited = client.get("/v1/benchmarks/draco-lite?limit=2").json()
    complete = client.get("/v1/benchmarks/draco-lite").json()

    assert limited["case_count"] == 2
    assert limited["total_case_count"] == 100
    assert limited["candidate_invocations"] == 2
    assert limited["url4"] != complete["url4"]
    assert complete["case_count"] == 100


def test_default_alias_resolves_without_a_catalog_fetch(client: TestClient) -> None:
    explicit = client.get(f"/v1/benchmarks/{DEFAULT_BENCHMARK_ID}?limit=1")
    default = client.get("/v1/benchmarks/default?limit=1")

    assert default.status_code == 200
    assert default.json() == explicit.json()


def test_resource_has_a_representation_specific_strong_etag(client: TestClient) -> None:
    one = client.get("/v1/benchmarks/draco-lite?limit=1")
    two = client.get("/v1/benchmarks/draco-lite?limit=2")

    assert "public" in one.headers["cache-control"]
    assert one.headers["etag"].startswith('"')
    assert one.headers["etag"] != two.headers["etag"]


def test_matching_if_none_match_gets_304_with_no_body(client: TestClient) -> None:
    etag = client.get("/v1/benchmarks/draco-lite?limit=1").headers["etag"]

    response = client.get(
        "/v1/benchmarks/draco-lite?limit=1",
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
    response = client.get("/v1/benchmarks/draco-lite", params={"limit": limit})

    assert response.status_code == 422


def test_planning_post_route_no_longer_exists(client: TestClient) -> None:
    response = client.post("/v1/benchmarks/draco-lite/plans", json={})

    assert response.status_code == 404


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "draco-lite/../../secret", "%2e%2e%2f"],
)
def test_a_traversal_shaped_id_is_never_served(client: TestClient, hostile: str) -> None:
    response = client.get(f"/v1/benchmarks/{hostile}")

    assert response.status_code in (404, 400)
    assert "root:" not in response.text
