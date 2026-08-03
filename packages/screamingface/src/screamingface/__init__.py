"""ScreamingFace — evaluate Models and Fusions on research Benchmarks."""

from screamingface import benchmarks, connections, events, models
from screamingface._default_client import close, configure, connect, disconnect, evaluate
from screamingface._ui.connections import ConnectionPanel
from screamingface.client import AsyncClient, Client
from screamingface.connections import Connection
from screamingface.discovery import BenchmarkInfo, ModelInfo
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
from screamingface.report import CandidateResult, Failure, MemberResult, Report, Usage
from screamingface.warnings import CoverageWarning, EvaluationWarning

__all__ = [
    "AsyncClient",
    "AuthenticationError",
    "BenchmarkInfo",
    "CandidateResult",
    "Client",
    "Connection",
    "ConnectionPanel",
    "CoverageWarning",
    "close",
    "configure",
    "connect",
    "connections",
    "disconnect",
    "Event",
    "EngineUnavailableError",
    "ExecutionError",
    "EvaluationWarning",
    "evaluate",
    "Failure",
    "Fusion",
    "MemberResult",
    "Model",
    "ModelInfo",
    "OperationInfo",
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
