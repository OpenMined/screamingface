"""ScreamingFace — evaluate Models and Fusions on research Benchmarks."""

from screamingface import benchmarks, connections, events, models
from screamingface._default_client import close, configure, connect, disconnect, evaluate
from screamingface._ui.connections import ConnectionPanel
from screamingface.client import AsyncClient, Client
from screamingface.connections import AsyncOAuthFlow, Connection, OAuthFlow
from screamingface.discovery import (
    Benchmark,
    BenchmarkInfo,
    ModelCapability,
    ModelDetails,
    ModelInfo,
    ModelParameter,
    ModelParameterSchema,
)
from screamingface.errors import (
    AuthenticationError,
    EngineUnavailableError,
    ExecutionError,
    PlanningError,
    ProviderConnectionError,
    ScreamingFaceError,
)
from screamingface.events import Event
from screamingface.fusion import Fusion
from screamingface.model import Model
from screamingface.operation import OperationInfo
from screamingface.recipe import Recipe
from screamingface.report import (
    CandidateResult,
    CaseGrade,
    CaseResult,
    Check,
    Evidence,
    EvidenceProducer,
    Failure,
    MemberResult,
    Report,
    Usage,
)
from screamingface.warnings import CoverageWarning, EvaluationWarning

__all__ = [
    "AsyncClient",
    "AuthenticationError",
    "Benchmark",
    "BenchmarkInfo",
    "CaseGrade",
    "CaseResult",
    "CandidateResult",
    "Check",
    "Client",
    "Connection",
    "ConnectionPanel",
    "AsyncOAuthFlow",
    "CoverageWarning",
    "close",
    "configure",
    "connect",
    "connections",
    "disconnect",
    "Evidence",
    "EvidenceProducer",
    "Event",
    "EngineUnavailableError",
    "ExecutionError",
    "EvaluationWarning",
    "evaluate",
    "Failure",
    "Fusion",
    "MemberResult",
    "Model",
    "ModelCapability",
    "ModelDetails",
    "ModelInfo",
    "ModelParameter",
    "ModelParameterSchema",
    "OperationInfo",
    "OAuthFlow",
    "PlanningError",
    "ProviderConnectionError",
    "Recipe",
    "Report",
    "ScreamingFaceError",
    "Usage",
    "benchmarks",
    "events",
    "models",
]
