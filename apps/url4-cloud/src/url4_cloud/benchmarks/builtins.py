"""Concrete Benchmarks selected by the URL4 Cloud deployment."""

from url4_cloud.benchmarks.draco.definition import DRACO, DRACO_LITE, DRACO_SMOKE
from url4_cloud.benchmarks.healthbench.definition import (
    HEALTHBENCH_WORST30,
)
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.registry import BenchmarkRegistry

# WHY: protocol-neutral registry machinery does not import concrete protocols. This composition
# module is the single place where this deployment chooses which Benchmark adapters to install.
# The former ifeval/lanl-ensemble and ifeval/self-corrective variants are RETIRED (OME-796):
# corrective loops are client-compiled candidates now, not benchmarks wearing costumes.
BUILTIN_BENCHMARKS = BenchmarkRegistry(
    (
        DRACO,
        DRACO_LITE,
        DRACO_SMOKE,
        IFEVAL,
        HEALTHBENCH_WORST30,
    )
)

__all__ = ["BUILTIN_BENCHMARKS"]
