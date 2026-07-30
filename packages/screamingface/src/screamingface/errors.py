"""Small public exception hierarchy at the SF Client/Engine boundary."""

from __future__ import annotations


class ScreamingFaceError(Exception):
    """Base class for failures that prevent the Client from returning a valid value."""


class _DiagnosticError(ScreamingFaceError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        permanent: bool | None = None,
        details: object = None,
    ) -> None:
        self.code = code
        self.status = status
        self.permanent = permanent
        self.details = details
        super().__init__(message)


class AuthenticationError(_DiagnosticError):
    """The configured SF Engine rejected caller authentication."""


class PlanningError(_DiagnosticError):
    """An Evaluation could not be resolved or validated safely."""


class ExecutionError(_DiagnosticError):
    """A Run ended without a valid Report."""


__all__ = [
    "AuthenticationError",
    "ExecutionError",
    "PlanningError",
    "ScreamingFaceError",
]
