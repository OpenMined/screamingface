"""Explicit registry of Engine-owned Benchmark definitions."""

from url4_cloud.benchmarks.base import Benchmark
from url4_cloud.benchmarks.draco.benchmark import DRACO_LITE

BENCHMARKS: dict[str, Benchmark] = {DRACO_LITE.id: DRACO_LITE}
DEFAULT_BENCHMARK_ID = DRACO_LITE.id

if DEFAULT_BENCHMARK_ID == "default" or "default" in BENCHMARKS:
    raise RuntimeError("'default' is reserved as the Benchmark route alias")
if any(key != benchmark.id for key, benchmark in BENCHMARKS.items()):
    raise RuntimeError("every Benchmark registry key must equal its definition id")

__all__ = ["BENCHMARKS", "DEFAULT_BENCHMARK_ID", "Benchmark"]
