"""``GET /v1/benchmarks`` and ``GET /v1/benchmarks/{id}`` — the benchmark catalog.

FEATURE: a client picks a benchmark and learns how to run it — data routes, judge, grading
protocol — without reading the image's url4.toml or guessing.

STORY: as someone about to submit a benchmark expression, I list the available benchmarks, fetch
one manifest, and read off the routes and judge settings it needs.

The manifests are CONSTANTS, not files: there is no path to traverse and no I/O to fail, so the
only failure a caller can provoke is an unknown id.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from url4_cloud import manifests
from url4_cloud.rest.benchmarks import router

pytestmark = pytest.mark.anyio


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# --- the registry itself ---------------------------------------------------------


def test_every_manifest_is_keyed_by_its_own_declared_id() -> None:
    """INVARIANT: the registry key IS the id in the text. They are two spellings of one fact, so
    a mismatch would make `/v1/benchmarks/{id}` serve a manifest that names a different id."""
    for key, text in manifests.MANIFESTS.items():
        assert manifests.field(text, "id") == key


def test_every_manifest_carries_the_fields_a_client_needs_to_run_it() -> None:
    required = ("id", "title", "description", "dataset")
    for key, text in manifests.MANIFESTS.items():
        for name in required:
            assert manifests.field(text, name), f"{key} is missing {name!r}"
        assert "  route: /draco/cases\n" in text
        assert "  criteria_route: /draco/criteria/{case_id}\n" in text
        assert "  route: /benchmark\n" in text


def test_the_registry_is_not_empty() -> None:
    assert manifests.MANIFESTS


# --- listing ---------------------------------------------------------------------


def test_listing_returns_an_envelope_not_a_bare_array(client: TestClient) -> None:
    """A bare array has nowhere to grow: adding pagination later would be a breaking change."""
    body = client.get("/v1/benchmarks").json()

    assert isinstance(body, dict)
    assert body["object"] == "list"
    assert isinstance(body["data"], list)


def test_listing_summarises_each_manifest_with_a_link_to_it(client: TestClient) -> None:
    entries = client.get("/v1/benchmarks").json()["data"]

    by_id = {e["id"]: e for e in entries}
    assert set(by_id) == set(manifests.MANIFESTS)
    assert client.get("/v1/benchmarks").json()["default"] == manifests.DEFAULT_BENCHMARK_ID
    for key, entry in by_id.items():
        assert entry["object"] == "benchmark"
        assert entry["href"] == f"/v1/benchmarks/{key}"
        assert entry["title"]
        assert entry["description"]


def test_listing_is_publicly_cacheable_with_a_validator(client: TestClient) -> None:
    r = client.get("/v1/benchmarks")

    assert "public" in r.headers["cache-control"]
    assert r.headers["etag"]


# --- fetching one ----------------------------------------------------------------


def test_a_manifest_is_served_verbatim_as_text(client: TestClient) -> None:
    """The manifest IS a string. Wrapping it in JSON would make every caller unescape it back."""
    key = next(iter(manifests.MANIFESTS))

    r = client.get(f"/v1/benchmarks/{key}")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/yaml")
    assert r.text == manifests.MANIFESTS[key]


def test_a_manifest_carries_a_strong_etag_and_public_caching(client: TestClient) -> None:
    key = next(iter(manifests.MANIFESTS))

    r = client.get(f"/v1/benchmarks/{key}")

    assert "public" in r.headers["cache-control"]
    assert r.headers["etag"].startswith('"')  # strong, not W/ — we serve exact bytes


def test_a_matching_if_none_match_gets_304_with_no_body(client: TestClient) -> None:
    key = next(iter(manifests.MANIFESTS))
    etag = client.get(f"/v1/benchmarks/{key}").headers["etag"]

    r = client.get(f"/v1/benchmarks/{key}", headers={"If-None-Match": etag})

    assert r.status_code == 304
    assert not r.content


def test_a_stale_if_none_match_gets_the_body(client: TestClient) -> None:
    key = next(iter(manifests.MANIFESTS))

    r = client.get(f"/v1/benchmarks/{key}", headers={"If-None-Match": '"stale"'})

    assert r.status_code == 200
    assert r.text == manifests.MANIFESTS[key]


def test_two_manifests_never_share_an_etag() -> None:
    """A shared validator would let a cache serve one benchmark's manifest for another."""
    tags = {manifests.etag_of(t) for t in manifests.MANIFESTS.values()}
    assert len(tags) == len(manifests.MANIFESTS)


# --- the only reachable error ----------------------------------------------------


def test_an_unknown_id_is_404_as_problem_json(client: TestClient) -> None:
    r = client.get("/v1/benchmarks/does-not-exist")

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 404


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "draco-lite/../../secret", "%2e%2e%2f"],
)
def test_a_traversal_shaped_id_is_never_served(client: TestClient, hostile: str) -> None:
    """INVARIANT: ids are dict keys, never path segments — there is nothing to traverse. This
    pins that the registry lookup, not the filesystem, is what answers."""
    r = client.get(f"/v1/benchmarks/{hostile}")

    assert r.status_code in (404, 400)
    assert "root:" not in r.text
