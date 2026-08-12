"""Concrete Benchmarks selected by the URL4 Cloud deployment."""

from url4_cloud.benchmarks.draco.definition import DRACO, DRACO_LITE, DRACO_SMOKE
from url4_cloud.benchmarks.healthbench.definition import (
    HEALTHBENCH_WORST30,
)
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_LANL_ENSEMBLE,
    IFEVAL_SELF_CORRECTIVE,
)
from url4_cloud.benchmarks.registry import BenchmarkRegistry

# WHY: protocol-neutral registry machinery does not import concrete protocols. This composition
# module is the single place where this deployment chooses which Benchmark adapters to install.
BUILTIN_BENCHMARKS = BenchmarkRegistry(
    (
        DRACO,
        DRACO_LITE,
        DRACO_SMOKE,
        IFEVAL,
        IFEVAL_LANL_ENSEMBLE,
        IFEVAL_SELF_CORRECTIVE,
        HEALTHBENCH_WORST30,
    )
)

__all__ = ["BUILTIN_BENCHMARKS"]
