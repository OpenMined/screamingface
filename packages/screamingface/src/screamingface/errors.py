"""Typed public failures at the ScreamingFace/engine boundary."""


class ScreamingFaceError(Exception):
    """Base class for ScreamingFace failures."""


class EngineConnectionError(ScreamingFaceError):
    """The configured URL4 engine could not be reached."""


class EngineProtocolError(ScreamingFaceError):
    """The engine violated the expected HTTP transport contract."""


class EngineProfileError(EngineProtocolError):
    """The ScreamingFace registry is missing, malformed, or incompatible."""


class EngineRequestTooLargeError(ScreamingFaceError):
    """A URL4 evaluation cannot fit within the engine's advertised HTTP limit."""

    def __init__(self, label: str, *, actual_bytes: int, allowed_bytes: int) -> None:
        self.actual_bytes = actual_bytes
        self.allowed_bytes = allowed_bytes
        super().__init__(
            f"{label} URL4 request target is {actual_bytes} bytes; "
            f"engine allows {allowed_bytes} bytes"
        )


class UnknownBenchmarkError(ScreamingFaceError):
    """The installed SDK catalog does not contain a requested benchmark."""


class UnknownModelError(ScreamingFaceError):
    """The configured engine does not advertise a requested model."""


class UnsupportedToolError(ScreamingFaceError):
    """A selected model cannot provide a benchmark-required tool."""


class UnsupportedReducerError(ScreamingFaceError):
    """The configured engine does not advertise a selected reducer."""


class InvalidBenchmarkError(ScreamingFaceError):
    """A benchmark definition or its source data is invalid."""
