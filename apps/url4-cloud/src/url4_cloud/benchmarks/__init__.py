"""Benchmark assets baked into the Runner image.

Benchmark preparation and aggregation are executed as subprocesses by declared ``[commands]``
routes. The registry exports remain available to local mode, where the control plane and Runner
intentionally share one process.
"""

from url4_cloud.benchmarks.registry import BENCHMARKS, DEFAULT_BENCHMARK_ID, benchmark

__all__ = ["BENCHMARKS", "DEFAULT_BENCHMARK_ID", "benchmark"]
