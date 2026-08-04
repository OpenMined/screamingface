"""Explicit registry and asset installation for Engine-owned Benchmarks."""

from collections.abc import Mapping
from pathlib import Path

from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark, BenchmarkFamily
from url4_cloud.benchmarks.draco.definition import DRACO
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_SELF_CORRECTIVE,
    IFEVAL_VERIFYING_ENSEMBLE,
)

BENCHMARKS: dict[str, Benchmark] = {
    DRACO.id: DRACO,
    IFEVAL.id: IFEVAL,
    IFEVAL_SELF_CORRECTIVE.id: IFEVAL_SELF_CORRECTIVE,
    IFEVAL_VERIFYING_ENSEMBLE.id: IFEVAL_VERIFYING_ENSEMBLE,
}
BENCHMARK_FAMILIES: dict[str, BenchmarkFamily] = {
    "draco": BenchmarkFamily(
        id="draco",
        title="DRACO",
        description="The DRACO deep-research Benchmark Family.",
        default_variant="canonical",
        variants=(DRACO,),
    ),
    "ifeval": BenchmarkFamily(
        id="ifeval",
        title="IFEval",
        description="Deterministic instruction-following evaluation.",
        default_variant="canonical",
        variants=(IFEVAL, IFEVAL_SELF_CORRECTIVE, IFEVAL_VERIFYING_ENSEMBLE),
    ),
}
DEFAULT_BENCHMARK_ID = "draco"
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
if set(BENCHMARK_FAMILIES) != {benchmark.family for benchmark in BENCHMARKS.values()}:
    raise RuntimeError("Benchmark Family registry must cover every installed Variant")


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
    "BENCHMARK_FAMILIES",
    "DEFAULT_ASSETS_ROOT",
    "DEFAULT_BENCHMARK_ID",
    "Benchmark",
    "BenchmarkFamily",
    "assets_root",
    "install_benchmarks",
]
