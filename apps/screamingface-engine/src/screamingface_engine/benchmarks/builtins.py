"""Concrete Benchmarks selected by the URL4 Cloud deployment."""

from screamingface_engine.benchmarks.draco.definition import DRACO
from screamingface_engine.benchmarks.healthbench.definition import (
    HEALTHBENCH_PROFESSIONAL,
    HEALTHBENCH_WORST30,
)
from screamingface_engine.benchmarks.ifeval.definition import IFEVAL
from screamingface_engine.benchmarks.registry import BenchmarkRegistry

# WHY: protocol-neutral registry machinery does not import concrete protocols. This composition
# module is the single place where this deployment chooses which Benchmark adapters to install.
# Candidate strategies are client-compiled Recipes, and development projections are not public
# Benchmarks. This registry contains only complete, independently meaningful benchmark identities.
BUILTIN_BENCHMARKS = BenchmarkRegistry(
    (
        DRACO,
        IFEVAL,
        HEALTHBENCH_WORST30,
        HEALTHBENCH_PROFESSIONAL,
    )
)

__all__ = ["BUILTIN_BENCHMARKS"]
