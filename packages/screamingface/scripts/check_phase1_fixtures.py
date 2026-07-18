"""Construct every Phase 0 public-contract fixture against the installed SDK."""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    fixtures = Path(__file__).parents[3] / "docs" / "spec" / "fixtures" / "ome_400"
    for name in (
        "in_memory_benchmark.py",
        "gpqa_benchmark.py",
        "draco_benchmark.py",
        "benchmark_walkthrough.py",
    ):
        runpy.run_path(str(fixtures / name))


if __name__ == "__main__":
    main()
