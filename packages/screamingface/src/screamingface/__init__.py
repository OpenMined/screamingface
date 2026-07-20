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
from screamingface.grades import CaseGrades, CriterionVerdict, Grade, GradeFailure, Grades
from screamingface.reducers import Reducer
from screamingface.report import MemberReport, Report
from screamingface.run import CaseResult, MemberResult, Run, RunFailure

__all__ = [
    "Aggregator",
    "Benchmark",
    "Case",
    "CaseGrades",
    "CaseResult",
    "Connection",
    "ConnectionRequiredError",
    "CriterionVerdict",
    "EngineConnectionError",
    "EngineProfileError",
    "EngineProtocolError",
    "EngineRequestTooLargeError",
    "Fusion",
    "Grade",
    "GradeFailure",
    "Grader",
    "Grades",
    "InvalidBenchmarkError",
    "MemberResult",
    "MemberReport",
    "OAuthFlow",
    "ProviderConnectionError",
    "Reducer",
    "Run",
    "RunFailure",
    "Report",
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
