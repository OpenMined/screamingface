"""Verify the executable OME-400 contract fixtures use the current public API."""

from __future__ import annotations

import runpy
from collections.abc import Mapping
from pathlib import Path

import screamingface as sf


def main() -> None:
    repo = Path(__file__).resolve().parents[3]
    fixtures = repo / "docs" / "spec" / "fixtures" / "ome_400"

    benchmark_modules = (
        "draco_benchmark.py",
        "gpqa_benchmark.py",
        "in_memory_benchmark.py",
    )
    for filename in benchmark_modules:
        namespace = runpy.run_path(str(fixtures / filename))
        benchmark = namespace.get("benchmark")
        if not isinstance(benchmark, sf.Benchmark):
            raise TypeError(f"{filename} does not expose an sf.Benchmark named 'benchmark'")

    walkthrough = runpy.run_path(str(fixtures / "benchmark_walkthrough.py"))
    _require(walkthrough, "fusion", sf.Fusion, "benchmark_walkthrough.py")
    for function_name in ("quickstart", "candidate_study", "inspect_report", "inspect_study"):
        value = walkthrough.get(function_name)
        if not callable(value):
            raise TypeError(f"benchmark_walkthrough.py does not expose callable {function_name!r}")


def _require(
    namespace: Mapping[str, object], name: str, expected: type[object], filename: str
) -> None:
    if not isinstance(namespace.get(name), expected):
        raise TypeError(f"{filename} does not expose {expected.__name__} named {name!r}")


if __name__ == "__main__":
    main()
