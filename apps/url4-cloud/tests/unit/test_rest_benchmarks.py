import pytest
from fastapi.testclient import TestClient

from url4_cloud.app import create_app
from url4_cloud.benchmarks._types import Benchmark


def _benchmark(value: str) -> Benchmark:
    return Benchmark(value, value.title(), f"id: {value}\n".encode(), {})


def test_an_unconfigured_engine_advertises_no_benchmarks() -> None:
    response = TestClient(create_app()).get("/v1/benchmarks")

    assert response.status_code == 200
    assert response.json() == {"object": "list", "default": None, "data": []}


def test_returns_installed_ids_and_the_explicit_default() -> None:
    app = create_app(
        benchmarks=(_benchmark("draco"), _benchmark("healthbench-lite")),
        default_benchmark="healthbench-lite",
    )

    assert TestClient(app).get("/v1/benchmarks").json() == {
        "object": "list",
        "default": "healthbench-lite",
        "data": [
            {"id": "draco", "object": "benchmark"},
            {"id": "healthbench-lite", "object": "benchmark"},
        ],
    }


@pytest.mark.parametrize(
    "values",
    [
        ("",),
        ("  ",),
        ("draco", "draco"),
        ("draco", 1),
    ],
)
def test_invalid_composition_is_refused_at_app_creation(values: tuple[object, ...]) -> None:
    benchmarks = tuple(_benchmark(value) if isinstance(value, str) else value for value in values)
    with pytest.raises((TypeError, ValueError)):
        create_app(benchmarks=benchmarks, default_benchmark="draco")  # type: ignore[arg-type]


@pytest.mark.parametrize("default", [None, "", " ", "missing"])
def test_installed_benchmarks_require_an_explicit_installed_default(
    default: str | None,
) -> None:
    with pytest.raises(ValueError, match="default_benchmark"):
        create_app(
            benchmarks=(_benchmark("draco"),),
            default_benchmark=default,
        )


def test_an_empty_catalogue_refuses_a_default() -> None:
    with pytest.raises(ValueError, match="requires at least one"):
        create_app(default_benchmark="draco")


def test_returns_the_exact_installed_manifest() -> None:
    benchmark = _benchmark("draco")
    response = TestClient(create_app(benchmarks=(benchmark,), default_benchmark="draco")).get(
        "/v1/benchmarks/draco/manifest"
    )

    assert response.status_code == 200
    assert response.content == benchmark.manifest
    assert response.headers["content-type"].startswith("application/yaml")


def test_unknown_benchmark_manifest_is_not_found() -> None:
    response = TestClient(create_app()).get("/v1/benchmarks/missing/manifest")

    assert response.status_code == 404


def test_the_route_is_published_as_catalogue_api() -> None:
    operation = create_app().openapi()["paths"]["/v1/benchmarks"]["get"]

    assert "Catalog" in operation["tags"]
