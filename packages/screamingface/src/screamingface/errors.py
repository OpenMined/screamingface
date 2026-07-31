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


class ProviderConnectionError(_DiagnosticError):
    """A provider connection could not be read or updated safely."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        code: str | None = None,
        status: int | None = None,
        permanent: bool | None = None,
    ) -> None:
        self.provider = provider
        super().__init__(
            message,
            code=code,
            status=status,
            permanent=permanent,
        )


__all__ = [
    "AuthenticationError",
    "ExecutionError",
    "PlanningError",
    "ProviderConnectionError",
    "ScreamingFaceError",
]
