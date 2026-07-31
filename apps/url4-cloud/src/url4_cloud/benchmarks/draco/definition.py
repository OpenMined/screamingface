"""The installed DRACO Lite benchmark definition."""

from __future__ import annotations

from url4_cloud.benchmarks.draco.cases import CASES
from url4_cloud.benchmarks.draco.family import build_draco_benchmark

BENCHMARK_ID = "draco-lite"
JUDGE_PASSES = 1
CRITERIA_PER_CASE = 10

DRACO_LITE = build_draco_benchmark(
    benchmark_id=BENCHMARK_ID,
    title="DRACO Lite",
    cases=CASES,
    criteria_per_case=CRITERIA_PER_CASE,
    judge_passes=JUDGE_PASSES,
    answer_output_tokens=4096,
    synthesis_output_tokens=4096,
    judge_output_tokens=4096,
    tools=("web_search", "web_fetch"),
)

__all__ = ["DRACO_LITE"]
