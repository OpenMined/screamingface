"""Typed public errors for actionable notebook failures."""


class ScreamingFaceError(Exception):
    """Base class for SDK failures."""


class EngineError(ScreamingFaceError):
    """The URL4 engine rejected a request or returned an invalid result."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "engine_error",
        status_code: int | None = None,
        request_expression: str | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.request_expression = request_expression
        super().__init__(message)


class EngineUnavailable(EngineError):
    """No URL4 engine could be reached at the configured address."""


class DatasetUnavailable(ScreamingFaceError):
    """A gated benchmark cannot be loaded in the current environment."""
