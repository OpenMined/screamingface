"""ScreamingFace — compose URL4-backed model fusions and measure their gain."""

from screamingface.errors import (
    AmbiguousProfile,
    DatasetUnavailable,
    FusionNotReady,
    GatewayError,
    GatewayUnavailable,
    LoginRequired,
    ProviderCallError,
    ScreamingFaceError,
)
from screamingface.fusion import Fusion
from screamingface.gateway import Connection, OAuthStart, ProviderCapability
from screamingface.models import models
from screamingface.results import ModelResult, Run, RunFailure
from screamingface.session import (
    Session,
    connect,
    connect_oauth,
    connections,
    current_session,
    disconnect,
    providers,
    reset_session,
    setup,
    shutdown,
    wait_for_connection,
)

__version__ = "0.1.0"

__all__ = [
    "AmbiguousProfile",
    "Connection",
    "DatasetUnavailable",
    "Fusion",
    "FusionNotReady",
    "GatewayError",
    "GatewayUnavailable",
    "LoginRequired",
    "ModelResult",
    "OAuthStart",
    "ProviderCapability",
    "ProviderCallError",
    "Run",
    "RunFailure",
    "ScreamingFaceError",
    "Session",
    "__version__",
    "connect",
    "connect_oauth",
    "connections",
    "current_session",
    "disconnect",
    "models",
    "providers",
    "reset_session",
    "setup",
    "shutdown",
    "wait_for_connection",
]
