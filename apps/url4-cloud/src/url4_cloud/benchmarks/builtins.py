"""Concrete Benchmarks selected by the URL4 Cloud deployment."""

from url4_cloud.benchmarks.draco.definition import DRACO
from url4_cloud.benchmarks.healthbench.definition import (
    HEALTHBENCH_WORST30,
)
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.registry import BenchmarkRegistry

# WHY: protocol-neutral registry machinery does not import concrete protocols. This composition
# module is the single place where this deployment chooses which Benchmark adapters to install.
# Candidate strategies are client-compiled Recipes, and development projections are not public
# Benchmarks. This registry contains only complete, independently meaningful benchmark identities.
BUILTIN_BENCHMARKS = BenchmarkRegistry(
    (
        DRACO,
        IFEVAL,
        HEALTHBENCH_WORST30,
    )
)

__all__ = ["BUILTIN_BENCHMARKS"]
