"""Explicit registry and asset installation for Engine-owned Benchmarks."""

from collections.abc import Collection, Mapping
from pathlib import Path

from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark, BenchmarkInstaller
from url4_cloud.benchmarks.draco.definition import DRACO, DRACO_LITE, DRACO_SMOKE
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_LANL_ENSEMBLE,
    IFEVAL_SELF_CORRECTIVE,
)

BENCHMARKS: dict[str, Benchmark] = {
    DRACO.id: DRACO,
    DRACO_LITE.id: DRACO_LITE,
    DRACO_SMOKE.id: DRACO_SMOKE,
    IFEVAL.id: IFEVAL,
    IFEVAL_SELF_CORRECTIVE.id: IFEVAL_SELF_CORRECTIVE,
    IFEVAL_LANL_ENSEMBLE.id: IFEVAL_LANL_ENSEMBLE,
}
DEFAULT_BENCHMARK_ID = "draco"
ASSETS_ENV = "URL4_BENCHMARK_ASSETS"
DEFAULT_ASSETS_ROOT = Path("/opt/benchmarks")

if DEFAULT_BENCHMARK_ID == "default" or "default" in BENCHMARKS:
    raise RuntimeError("'default' is reserved as the Benchmark route alias")
if any(key != benchmark.id for key, benchmark in BENCHMARKS.items()):
    raise RuntimeError("every Benchmark registry key must equal its definition id")


def assets_root(env: Mapping[str, str]) -> Path:
    """Resolve the one filesystem dependency shared by Benchmark runtimes."""

    return Path(env.get(ASSETS_ENV) or DEFAULT_ASSETS_ROOT)


def install_benchmarks(
    node: Url4Node,
    root: Path,
    *,
    model_routes: Collection[str] = (),
) -> None:
    """Install every registered Benchmark's runtime routes into one Runner world."""

    declared_models = frozenset(model_routes)
    installed: set[BenchmarkInstaller] = set()
    for benchmark in BENCHMARKS.values():
        if benchmark.install in installed:
            continue
        benchmark.install(node, root, declared_models)
        installed.add(benchmark.install)


__all__ = [
    "ASSETS_ENV",
    "BENCHMARKS",
    "DEFAULT_ASSETS_ROOT",
    "DEFAULT_BENCHMARK_ID",
    "Benchmark",
    "assets_root",
    "install_benchmarks",
]
