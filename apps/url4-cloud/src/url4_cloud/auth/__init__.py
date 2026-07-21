"""url4_cloud.auth — capability topic + JWT + RFC 9457 Bearer guard (docs/protocol.md §7)."""

from url4_cloud.auth.dependencies import Clock, VerifiedClaims, verified_claims
from url4_cloud.auth.errors import (
    AuthError,
    IatWindowExceeded,
    InvalidToken,
    MissingCredentials,
    MissingIat,
    TokenExpired,
)
from url4_cloud.auth.jwt import JwtCodec
from url4_cloud.auth.problem import (
    PROBLEM_MEDIA_TYPE,
    Problem,
    ProblemException,
    install_problem_handlers,
    problem_exception_handler,
)
from url4_cloud.auth.token import new_topic

__all__ = [
    "PROBLEM_MEDIA_TYPE",
    "AuthError",
    "Clock",
    "IatWindowExceeded",
    "InvalidToken",
    "JwtCodec",
    "MissingCredentials",
    "MissingIat",
    "Problem",
    "ProblemException",
    "TokenExpired",
    "VerifiedClaims",
    "install_problem_handlers",
    "new_topic",
    "problem_exception_handler",
    "verified_claims",
]
