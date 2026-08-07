"""Public definition, registry, and installation surface for Engine-owned Benchmarks."""

from url4_cloud.benchmarks.definition import (
    Benchmark,
    BenchmarkInstaller,
    candidate,
    chat_input,
)
from url4_cloud.benchmarks.draco.definition import DRACO, DRACO_LITE, DRACO_SMOKE
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_SELF_CORRECTIVE,
    IFEVAL_VERIFYING_ENSEMBLE,
)
from url4_cloud.benchmarks.registry import (
    BENCHMARK_ASSETS_ENV,
    DEFAULT_BENCHMARK_ASSETS_ROOT,
    EMPTY_BENCHMARKS,
    BenchmarkRegistry,
    assets_root,
)

BENCHMARKS = BenchmarkRegistry(
    (
        DRACO,
        DRACO_LITE,
        DRACO_SMOKE,
        IFEVAL,
        IFEVAL_SELF_CORRECTIVE,
        IFEVAL_VERIFYING_ENSEMBLE,
    )
)

__all__ = [
    "BENCHMARK_ASSETS_ENV",
    "DEFAULT_BENCHMARK_ASSETS_ROOT",
    "BENCHMARKS",
    "Benchmark",
    "BenchmarkInstaller",
    "BenchmarkRegistry",
    "EMPTY_BENCHMARKS",
    "assets_root",
    "candidate",
    "chat_input",
]
