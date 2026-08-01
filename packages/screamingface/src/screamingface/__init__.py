"""ScreamingFace — evaluate Models and Fusions on research Benchmarks."""

from screamingface import benchmarks, connections, events, models
from screamingface._default_client import connect, disconnect, evaluate
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
from screamingface.recipe import Recipe
from screamingface.report import CandidateResult, Failure, MemberResult, Report, Usage

__all__ = [
    "AsyncClient",
    "AuthenticationError",
    "BenchmarkInfo",
    "CandidateResult",
    "Client",
    "Connection",
    "ConnectionPanel",
    "connect",
    "connections",
    "disconnect",
    "Event",
    "EngineUnavailableError",
    "ExecutionError",
    "evaluate",
    "Failure",
    "Fusion",
    "MemberResult",
    "Model",
    "ModelInfo",
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
