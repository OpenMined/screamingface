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
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_SELF_CORRECTIVE,
    MAX_ATTEMPTS,
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
        benchmark = BENCHMARKS[key]
        expected: dict[str, object] = {
            "object": "benchmark",
            "id": key,
            "variant": benchmark.variant,
            "title": benchmark.title,
            "description": benchmark.description,
            "href": f"/v1/benchmarks/{key}",
        }
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
    assert set(body) == {
        "schema",
        "id",
        "variant",
        "title",
        "description",
        "revision",
        "case_count",
        "url4",
    }
    assert body["schema"] == "screamingface.benchmark.v1"
    assert body["id"] == "draco"
    assert body["variant"] == "canonical"
    assert body["revision"] == REVISION
    assert body["case_count"] == 100
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


def test_ifeval_is_the_complete_canonical_judge_free_url4(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/ifeval?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "screamingface.benchmark.v1"
    assert body["id"] == "ifeval"
    assert body["variant"] == "canonical"
    assert body["revision"] == IFEVAL_REVISION
    assert body["case_count"] == IFEVAL_CASE_COUNT
    assert render(build(body["url4"])) == body["url4"]
    assert body["url4"].count("/candidate") == 1
    assert "$item.input" in body["url4"]
    assert f"{IFEVAL_ROUTE_PREFIX}/check" in body["url4"]
    assert f"{IFEVAL_ROUTE_PREFIX}/aggregate" in body["url4"]
    # No model node of any kind: the only routes are /candidate and the benchmark's own.
    assert "openrouter/" not in body["url4"]
    assert "judge" not in body["url4"]


def test_ifeval_installed_case_count_is_the_full_dataset(client: TestClient) -> None:
    assert IFEVAL_CASE_COUNT == 541


def test_ifeval_protocols_are_three_independently_executable_benchmarks(
    client: TestClient,
) -> None:
    resources = {
        benchmark_id: client.get(f"/v1/benchmarks/{benchmark_id}", params={"limit": 1}).json()
        for benchmark_id in (
            "ifeval",
            "ifeval/self-corrective",
            "ifeval/verifying-ensemble",
        )
    }

    assert set(resources) == {resource["id"] for resource in resources.values()}
    assert {resource["variant"] for resource in resources.values()} == {
        "canonical",
        "self-corrective",
        "verifying-ensemble",
    }
    assert len({resource["revision"] for resource in resources.values()}) == 3
    for resource in resources.values():
        assert resource["schema"] == "screamingface.benchmark.v1"
        assert resource["case_count"] == IFEVAL_CASE_COUNT
        assert render(build(resource["url4"])) == resource["url4"]
    assert resources["ifeval"]["url4"].count("$candidate") > 0
    assert resources["ifeval/self-corrective"]["url4"].count("$candidate") > 0
    memberwise = resources["ifeval/verifying-ensemble"]["url4"]
    assert "$candidate_members" in memberwise
    assert "$candidate_synthesizer" in memberwise
    assert "$candidate_model_member_" not in memberwise
    memberwise_description = resources["ifeval/verifying-ensemble"]["description"]
    assert "inspired by" in memberwise_description
    assert "all three attempts execute" in memberwise_description
    assert "The LANL iterative-correction protocol" not in memberwise_description


def test_ifeval_self_corrective_is_a_distinct_complete_variant(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/ifeval/self-corrective?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == IFEVAL_SELF_CORRECTIVE.revision
    assert body["case_count"] == IFEVAL_CASE_COUNT
    assert render(build(body["url4"])) == body["url4"]
    # Three unrolled answer attempts plus two self-authored feedback calls per case.
    assert body["url4"].count("/candidate") == MAX_ATTEMPTS + (MAX_ATTEMPTS - 1)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert f"$item.id:{attempt}" in body["url4"]
    assert body["url4"].count("!'feedback'") == MAX_ATTEMPTS - 1
    assert "openrouter/" not in body["url4"]


def test_limit_selects_cases_before_the_expression_is_returned(client: TestClient) -> None:
    limited = client.get("/v1/benchmarks/draco?limit=2").json()
    complete = client.get("/v1/benchmarks/draco").json()

    assert limited["case_count"] == complete["case_count"] == 100
    assert limited["url4"] != complete["url4"]
    assert "iteration.slice=0:2" in limited["url4"]
    assert "iteration.slice=" not in complete["url4"]


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


def test_benchmark_resources_are_read_only(client: TestClient) -> None:
    response = client.post("/v1/benchmarks/draco/plans", json={})

    assert response.status_code == 405


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "draco/../../secret", "%2e%2e%2f"],
)
def test_a_traversal_shaped_id_is_never_served(client: TestClient, hostile: str) -> None:
    response = client.get(f"/v1/benchmarks/{hostile}")

    assert response.status_code in (404, 400)
    assert "root:" not in response.text
