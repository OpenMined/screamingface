"""The one explicit registry of benchmarks installed in this image."""

from __future__ import annotations

import re
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

# WHY: a terminal `-v<digits>` is RESERVED for the exam version (`draco-lite-v1`);
# addresses themselves never end that way.
_VERSION_SUFFIX = re.compile(r"-v\d+$")


def benchmark(benchmark_id: str) -> Benchmark:
    # INVARIANT: accepts the address (`draco-lite`) or the exact versioned exam identity
    # from the manifest (`draco-lite-v1`); a version mismatch is an error, never a
    # silent fallback to whichever version happens to be installed.
    address = _VERSION_SUFFIX.sub("", benchmark_id)
    selected = BENCHMARKS.get(address)
    if selected is not None and benchmark_id in (selected.id, selected.versioned_id):
        return selected
    installed = sorted(entry.versioned_id for entry in BENCHMARKS.values())
    raise ValueError(f"unknown benchmark {benchmark_id!r}; installed: {installed}")


__all__ = ["BENCHMARKS", "DEFAULT_BENCHMARK_ID", "benchmark"]
