"""Installed deterministic benchmark handlers.

These handlers own data loading and scoring only. Candidate, synthesis, and judge model calls
remain explicit nodes in the URL4 expression and therefore never occur in this package.
"""

from url4_cloud.benchmarks.registry import BENCHMARKS, DEFAULT_BENCHMARK_ID, benchmark

__all__ = ["BENCHMARKS", "DEFAULT_BENCHMARK_ID", "benchmark"]
