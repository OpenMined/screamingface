"""The installed real-model DRACO smoke benchmark."""

from __future__ import annotations

from url4_cloud.benchmarks.draco.cases import SMOKE_CASES
from url4_cloud.benchmarks.draco.family import build_draco_benchmark

BENCHMARK_ID = "draco-smoke"
JUDGE_PASSES = 1
CRITERIA_PER_CASE = 1

DRACO_SMOKE = build_draco_benchmark(
    benchmark_id=BENCHMARK_ID,
    title="DRACO Smoke",
    cases=SMOKE_CASES,
    criteria_per_case=CRITERIA_PER_CASE,
    judge_passes=JUDGE_PASSES,
    answer_output_tokens=1024,
    synthesis_output_tokens=1024,
    judge_output_tokens=512,
    tools=(),
)

__all__ = ["DRACO_SMOKE"]
