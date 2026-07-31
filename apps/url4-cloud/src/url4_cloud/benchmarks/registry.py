"""The one explicit registry of benchmarks installed in this image."""

from __future__ import annotations

from types import MappingProxyType

from url4_cloud.benchmarks._types import Benchmark
from url4_cloud.benchmarks.draco import DRACO_LITE, DRACO_SMOKE

BENCHMARKS = MappingProxyType(
    {
        DRACO_SMOKE.id: DRACO_SMOKE,
        DRACO_LITE.id: DRACO_LITE,
    }
)
DEFAULT_BENCHMARK_ID = DRACO_SMOKE.id


def benchmark(benchmark_id: str) -> Benchmark:
    try:
        return BENCHMARKS[benchmark_id]
    except KeyError:
        raise ValueError(
            f"unknown benchmark {benchmark_id!r}; installed: {sorted(BENCHMARKS)}"
        ) from None


__all__ = ["BENCHMARKS", "DEFAULT_BENCHMARK_ID", "benchmark"]
