"""One deployment declaration drives runtime discovery and image asset preparation."""

from __future__ import annotations

from pathlib import Path

import pytest

from screamingface_engine.benchmarks.builtins import (
    BUILTIN_BENCHMARKS,
    BUILTIN_DEPLOYMENT,
)
from screamingface_engine.benchmarks.definition import Benchmark
from screamingface_engine.benchmarks.deployment import (
    BenchmarkAssetBundle,
    BenchmarkDeployment,
    BenchmarkRegistration,
)
from url4 import Text


def _benchmark(benchmark_id: str) -> Benchmark:
    return Benchmark(
        id=benchmark_id,
        title=benchmark_id,
        description=f"{benchmark_id} description",
        revision="revision-1",
        case_count=1,
        build=lambda _selected: Text("protocol"),
    )


def test_deployment_prepares_each_shared_bundle_once_in_stable_directories(
    tmp_path: Path,
) -> None:
    calls: list[Path] = []
    shared = BenchmarkAssetBundle(id="shared", prepare=calls.append)
    alpha = BenchmarkAssetBundle(id="alpha", prepare=calls.append)
    deployment = BenchmarkDeployment(
        (
            BenchmarkRegistration(_benchmark("one"), asset_bundle=shared),
            BenchmarkRegistration(_benchmark("two"), asset_bundle=shared),
            BenchmarkRegistration(_benchmark("three"), asset_bundle=alpha),
        )
    )

    prepared = deployment.prepare_assets(tmp_path)

    assert tuple(benchmark.id for benchmark in deployment.benchmarks) == (
        "one",
        "three",
        "two",
    )
    assert calls == [tmp_path / "alpha", tmp_path / "shared"]
    assert prepared == tuple(calls)
    assert all(path.is_dir() for path in prepared)


def test_conflicting_physical_bundles_cannot_share_a_directory_id() -> None:
    first = BenchmarkAssetBundle(id="shared", prepare=lambda _out: None)
    second = BenchmarkAssetBundle(id="shared", prepare=lambda _out: None)

    with pytest.raises(ValueError, match="conflicting BenchmarkAssetBundles"):
        BenchmarkDeployment(
            (
                BenchmarkRegistration(_benchmark("one"), asset_bundle=first),
                BenchmarkRegistration(_benchmark("two"), asset_bundle=second),
            )
        )


@pytest.mark.parametrize("bundle_id", ("../escape", "nested/path", "UPPER", "-leading"))
def test_asset_bundle_ids_are_safe_directory_names(bundle_id: str) -> None:
    with pytest.raises(ValueError, match="path-safe"):
        BenchmarkAssetBundle(id=bundle_id, prepare=lambda _out: None)


def test_builtins_are_registered_with_their_physical_asset_bundles() -> None:
    registrations = {
        registration.benchmark.id: registration.asset_bundle.id
        for registration in BUILTIN_DEPLOYMENT.registrations
    }

    assert BUILTIN_DEPLOYMENT.benchmarks is BUILTIN_BENCHMARKS
    assert registrations == {
        "draco": "draco",
        "draco-3pass": "draco",
        "ifeval": "ifeval",
        "healthbench-worst30": "healthbench",
        "healthbench-professional": "healthbench",
    }


def test_benchmark_image_invokes_only_the_registered_asset_orchestrator() -> None:
    dockerfile = Path(__file__).parents[2] / "Dockerfile.benchmark"
    body = dockerfile.read_text(encoding="utf-8")

    assert "-m screamingface_engine.benchmarks.prepare --root /opt/benchmarks" in body
    assert "screamingface_engine.benchmarks.draco.prepare" not in body
