"""ScreamingFace — URL4-native model fusions and benchmark comparison."""

from screamingface.errors import (
    DatasetUnavailable,
    EngineError,
    EngineUnavailable,
    ScreamingFaceError,
)
from screamingface.fusion import Fusion
from screamingface.models import models
from screamingface.reducers import MajorityVote, Synthesize
from screamingface.results import ModelResult, Run, RunFailure
from screamingface.session import (
    Session,
    config,
    current_session,
    reset_session,
    shutdown,
)

__version__ = "0.2.0"

__all__ = [
    "DatasetUnavailable",
    "EngineError",
    "EngineUnavailable",
    "Fusion",
    "MajorityVote",
    "ModelResult",
    "Run",
    "RunFailure",
    "Synthesize",
    "ScreamingFaceError",
    "Session",
    "__version__",
    "current_session",
    "models",
    "reset_session",
    "config",
    "shutdown",
]
