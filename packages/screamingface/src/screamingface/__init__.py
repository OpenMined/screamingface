"""ScreamingFace — evaluate Models and Fusions on research Benchmarks."""

from screamingface import benchmarks, events, models, reducers
from screamingface.client import AsyncClient, Client
from screamingface.discovery import BenchmarkInfo, ModelInfo
from screamingface.errors import (
    AuthenticationError,
    ExecutionError,
    PlanningError,
    ScreamingFaceError,
)
from screamingface.events import Event
from screamingface.fusion import Fusion
from screamingface.model import Model
from screamingface.recipe import Recipe
from screamingface.reducers import Reducer
from screamingface.report import CandidateResult, Failure, MemberResult, Report, Usage

__all__ = [
    "AsyncClient",
    "AuthenticationError",
    "BenchmarkInfo",
    "CandidateResult",
    "Client",
    "Event",
    "ExecutionError",
    "Failure",
    "Fusion",
    "MemberResult",
    "Model",
    "ModelInfo",
    "PlanningError",
    "Recipe",
    "Reducer",
    "Report",
    "ScreamingFaceError",
    "Usage",
    "benchmarks",
    "events",
    "models",
    "reducers",
]
