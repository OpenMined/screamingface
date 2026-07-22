"""ScreamingFace — URL4-native model fusions and benchmark comparison."""

from screamingface import aggregators, benchmarks, connections, graders, models, reducers, tools
from screamingface._config import config
from screamingface.aggregators import Aggregator
from screamingface.benchmark import Benchmark, Case
from screamingface.connections import Connection, OAuthFlow, connect, disconnect
from screamingface.errors import (
    AuthMethodRequiredError,
    ConnectionRequiredError,
    EngineConnectionError,
    EngineProfileError,
    EngineProtocolError,
    EngineRequestTooLargeError,
    InvalidBenchmarkError,
    ProviderConnectionError,
    ScreamingFaceError,
    SecureTransportRequiredError,
    UnknownBenchmarkError,
    UnknownModelError,
    UnknownProviderError,
    UnsupportedAuthMethodError,
    UnsupportedReducerError,
    UnsupportedToolError,
)
from screamingface.fusion import Fusion
from screamingface.graders import Grader
from screamingface.model import Model
from screamingface.recipe import Recipe
from screamingface.reducers import Reducer
from screamingface.report import (
    CandidateReport,
    EvaluationFailure,
    MemberReport,
    Report,
    StudyReport,
)

__all__ = [
    "Aggregator",
    "Benchmark",
    "Case",
    "CandidateReport",
    "Connection",
    "ConnectionRequiredError",
    "EngineConnectionError",
    "EngineProfileError",
    "EngineProtocolError",
    "EngineRequestTooLargeError",
    "Fusion",
    "Grader",
    "InvalidBenchmarkError",
    "EvaluationFailure",
    "MemberReport",
    "Model",
    "OAuthFlow",
    "ProviderConnectionError",
    "Reducer",
    "Recipe",
    "Report",
    "StudyReport",
    "ScreamingFaceError",
    "SecureTransportRequiredError",
    "UnknownBenchmarkError",
    "UnknownModelError",
    "UnknownProviderError",
    "AuthMethodRequiredError",
    "UnsupportedAuthMethodError",
    "UnsupportedReducerError",
    "UnsupportedToolError",
    "aggregators",
    "benchmarks",
    "connect",
    "connections",
    "config",
    "disconnect",
    "graders",
    "models",
    "reducers",
    "tools",
]
