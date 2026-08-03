"""Explicit registry and asset installation for Engine-owned Benchmarks."""

from collections.abc import Mapping
from pathlib import Path

from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark
from url4_cloud.benchmarks.draco.definition import DRACO
from url4_cloud.benchmarks.ifeval.corrective import IFEVAL_CORRECTIVE
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.ensemble import IFEVAL_CORRECTIVE_ENSEMBLE

BENCHMARKS: dict[str, Benchmark] = {
    DRACO.id: DRACO,
    IFEVAL.id: IFEVAL,
    IFEVAL_CORRECTIVE.id: IFEVAL_CORRECTIVE,
    IFEVAL_CORRECTIVE_ENSEMBLE.id: IFEVAL_CORRECTIVE_ENSEMBLE,
}
DEFAULT_BENCHMARK_ID = DRACO.id
ASSETS_ENV = "URL4_BENCHMARK_ASSETS"
DEFAULT_ASSETS_ROOT = Path("/opt/benchmarks")

if DEFAULT_BENCHMARK_ID == "default" or "default" in BENCHMARKS:
    raise RuntimeError("'default' is reserved as the Benchmark route alias")
if any(key != benchmark.id for key, benchmark in BENCHMARKS.items()):
    raise RuntimeError("every Benchmark registry key must equal its definition id")
for family in {benchmark.family for benchmark in BENCHMARKS.values()}:
    members = [benchmark for benchmark in BENCHMARKS.values() if benchmark.family == family]
    if len({benchmark.variant for benchmark in members}) != len(members):
        raise RuntimeError(f"Benchmark family {family!r} contains duplicate variants")
    if len({benchmark.install for benchmark in members}) != 1:
        raise RuntimeError(f"Benchmark family {family!r} must share one runtime installer")


def assets_root(env: Mapping[str, str]) -> Path:
    """Resolve the one filesystem dependency shared by Benchmark runtimes."""

    return Path(env.get(ASSETS_ENV) or DEFAULT_ASSETS_ROOT)


def install_benchmarks(node: Url4Node, root: Path) -> None:
    """Install every registered Benchmark's runtime routes into one Runner world."""

    installed: set[str] = set()
    for benchmark in BENCHMARKS.values():
        if benchmark.family in installed:
            continue
        benchmark.install(node, root / benchmark.family)
        installed.add(benchmark.family)


__all__ = [
    "ASSETS_ENV",
    "BENCHMARKS",
    "DEFAULT_ASSETS_ROOT",
    "DEFAULT_BENCHMARK_ID",
    "Benchmark",
    "assets_root",
    "install_benchmarks",
]
