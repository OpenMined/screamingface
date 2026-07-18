"""ScreamingFace — URL4-native model fusions and benchmark comparison."""

from screamingface import aggregators, benchmarks, graders, models, reducers
from screamingface._config import config
from screamingface.aggregators import Aggregator
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import (
    EngineConnectionError,
    EngineProfileError,
    EngineProtocolError,
    InvalidBenchmarkError,
    ScreamingFaceError,
    UnknownBenchmarkError,
    UnknownModelError,
    UnsupportedReducerError,
    UnsupportedToolError,
)
from screamingface.fusion import Fusion
from screamingface.graders import Grader
from screamingface.reducers import Reducer

__all__ = [
    "Aggregator",
    "Benchmark",
    "Case",
    "EngineConnectionError",
    "EngineProfileError",
    "EngineProtocolError",
    "Fusion",
    "Grader",
    "InvalidBenchmarkError",
    "Reducer",
    "ScreamingFaceError",
    "UnknownBenchmarkError",
    "UnknownModelError",
    "UnsupportedReducerError",
    "UnsupportedToolError",
    "aggregators",
    "benchmarks",
    "config",
    "graders",
    "models",
    "reducers",
]
