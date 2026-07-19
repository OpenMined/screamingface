"""ScreamingFace — URL4-native model fusions and benchmark comparison."""

from screamingface import aggregators, benchmarks, graders, models, reducers
from screamingface._config import config
from screamingface.aggregators import Aggregator
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import (
    EngineConnectionError,
    EngineProfileError,
    EngineProtocolError,
    EngineRequestTooLargeError,
    InvalidBenchmarkError,
    ScreamingFaceError,
    UnknownBenchmarkError,
    UnknownModelError,
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
    "Reducer",
    "Run",
    "RunFailure",
    "Report",
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
