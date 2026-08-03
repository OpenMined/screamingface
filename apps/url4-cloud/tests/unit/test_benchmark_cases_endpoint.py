"""The paginated benchmark-cases resource on the Engine control plane.

FEATURE: benchmark researcher discovery (OME-722/OME-723) — a researcher reads a
benchmark's actual prompts through plain REST before spending money evaluating.
STORY: as a researcher, `sf.benchmarks.get("ifeval").cases(limit=5)` shows me real
prompts; the same contract later feeds the web frontend unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from url4_cloud.benchmarks import ASSETS_ENV, DEFAULT_BENCHMARK_ID
from url4_cloud.rest.benchmarks import router

pytestmark = pytest.mark.anyio

DRACO_TOTAL = 7
IFEVAL_TOTAL = 5


@pytest.fixture
def assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # WHY: the route reads the SAME prepared cases.json the runtime serves — the tests
    # build prepared-shape fixtures for both installed families under one assets root.
    draco_dir = tmp_path / "draco"
    draco_dir.mkdir()
    draco_rows = [
        # INVARIANT (answer-key discipline): extra prepared columns such as draco's
        # `domain` exist in the file but must NEVER appear in the response.
        {"id": index + 1, "input": f"draco question {index + 1}", "domain": "finance"}
        for index in range(DRACO_TOTAL)
    ]
    (draco_dir / "cases.json").write_text(json.dumps(draco_rows), encoding="utf-8")
    ifeval_dir = tmp_path / "ifeval"
    ifeval_dir.mkdir()
    ifeval_rows = [
        {"id": index + 1, "input": f"ifeval prompt {index + 1}"} for index in range(IFEVAL_TOTAL)
    ]
    (ifeval_dir / "cases.json").write_text(json.dumps(ifeval_rows), encoding="utf-8")
    monkeypatch.setenv(ASSETS_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture
def client(assets: Path) -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_defaults_return_the_first_page_with_pagination_envelope(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/draco/cases")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body == {
        "object": "list",
        "benchmark": "draco",
        "revision": body["revision"],
        "total": DRACO_TOTAL,
        "limit": 50,
        "offset": 0,
        "data": body["data"],
    }
    assert isinstance(body["revision"], str) and body["revision"]
    assert len(body["data"]) == DRACO_TOTAL
    assert body["data"][0] == {"id": 1, "input": "draco question 1"}


def test_response_rows_carry_exactly_id_and_input(client: TestClient) -> None:
    # INVARIANT: the answer-key discipline — no key beyond id/input ever leaves the
    # Engine through this route, even when the prepared file has extra columns.
    body = client.get("/v1/benchmarks/draco/cases").json()

    assert body["data"]
    for row in body["data"]:
        assert set(row) == {"id", "input"}


def test_limit_slices_and_offset_walks_the_case_list(client: TestClient) -> None:
    first = client.get("/v1/benchmarks/draco/cases", params={"limit": 3}).json()
    second = client.get("/v1/benchmarks/draco/cases", params={"limit": 3, "offset": 3}).json()
    tail = client.get("/v1/benchmarks/draco/cases", params={"limit": 3, "offset": 6}).json()

    assert [row["id"] for row in first["data"]] == [1, 2, 3]
    assert [row["id"] for row in second["data"]] == [4, 5, 6]
    assert [row["id"] for row in tail["data"]] == [7]
    for body, offset in ((first, 0), (second, 3), (tail, 6)):
        assert (body["total"], body["limit"], body["offset"]) == (DRACO_TOTAL, 3, offset)


def test_out_of_range_offset_is_an_empty_page_not_an_error(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/draco/cases", params={"offset": 999})

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["total"] == DRACO_TOTAL


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"limit": -1}, {"offset": -1}])
def test_out_of_bounds_paging_parameters_are_422(
    client: TestClient, params: dict[str, int]
) -> None:
    response = client.get("/v1/benchmarks/draco/cases", params=params)

    assert response.status_code == 422


def test_default_alias_serves_the_default_benchmark(client: TestClient) -> None:
    explicit = client.get(f"/v1/benchmarks/{DEFAULT_BENCHMARK_ID}/cases", params={"limit": 2})
    default = client.get("/v1/benchmarks/default/cases", params={"limit": 2})

    assert default.status_code == 200
    assert default.json() == explicit.json()


def test_ifeval_cases_are_served_through_the_same_generic_route(client: TestClient) -> None:
    body = client.get("/v1/benchmarks/ifeval/cases", params={"limit": 2}).json()

    assert body["benchmark"] == "ifeval"
    assert body["total"] == IFEVAL_TOTAL
    assert body["data"] == [
        {"id": 1, "input": "ifeval prompt 1"},
        {"id": 2, "input": "ifeval prompt 2"},
    ]


def test_unknown_benchmark_is_404_problem_json(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/does-not-exist/cases")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404


def test_missing_assets_are_503_benchmark_unavailable(client: TestClient, assets: Path) -> None:
    # WHY: a control plane deployed without the benchmark assets must fail LOUDLY with
    # the node-route error code, not pretend the benchmark has zero cases.
    (assets / "draco" / "cases.json").unlink()

    response = client.get("/v1/benchmarks/draco/cases")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 503
    assert body["code"] == "benchmark_unavailable"


def test_malformed_assets_are_503_not_a_crash(client: TestClient, assets: Path) -> None:
    (assets / "draco" / "cases.json").write_text("{not json", encoding="utf-8")

    response = client.get("/v1/benchmarks/draco/cases")

    assert response.status_code == 503
    assert response.json()["code"] == "benchmark_unavailable"


def test_pages_are_cacheable_with_representation_specific_etags(client: TestClient) -> None:
    one = client.get("/v1/benchmarks/draco/cases", params={"limit": 2})
    two = client.get("/v1/benchmarks/draco/cases", params={"limit": 2, "offset": 2})

    assert "public" in one.headers["cache-control"]
    assert one.headers["etag"].startswith('"')
    assert one.headers["etag"] != two.headers["etag"]


def test_matching_if_none_match_gets_304_with_no_body(client: TestClient) -> None:
    etag = client.get("/v1/benchmarks/draco/cases").headers["etag"]

    response = client.get("/v1/benchmarks/draco/cases", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert not response.content
