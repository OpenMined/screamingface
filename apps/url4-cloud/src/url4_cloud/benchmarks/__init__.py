"""Public definition and installation surface for Engine-owned Benchmarks."""

from url4_cloud.benchmarks.definition import (
    CANDIDATE_REF,
    Benchmark,
    BenchmarkInstaller,
    candidate,
    link_candidate,
)
from url4_cloud.benchmarks.draco.definition import DRACO, DRACO_LITE, DRACO_SMOKE
from url4_cloud.benchmarks.registry import (
    BENCHMARK_ASSETS_ENV,
    DEFAULT_BENCHMARK_ASSETS_ROOT,
    EMPTY_BENCHMARKS,
    BenchmarkRegistry,
    assets_root,
)

BENCHMARKS = BenchmarkRegistry((DRACO, DRACO_LITE, DRACO_SMOKE))

__all__ = [
    "BENCHMARK_ASSETS_ENV",
    "CANDIDATE_REF",
    "BENCHMARKS",
    "DEFAULT_BENCHMARK_ASSETS_ROOT",
    "Benchmark",
    "BenchmarkInstaller",
    "BenchmarkRegistry",
    "EMPTY_BENCHMARKS",
    "assets_root",
    "candidate",
    "link_candidate",
]
