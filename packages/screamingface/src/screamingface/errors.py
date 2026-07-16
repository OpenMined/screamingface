"""Typed public errors for actionable notebook failures."""


class ScreamingFaceError(Exception):
    """Base class for SDK failures."""


class GatewayError(ScreamingFaceError):
    """AI Gateway returned an invalid or unsuccessful response."""


class GatewayUnavailable(GatewayError):
    """No configured AI Gateway could be reached."""


class LoginRequired(GatewayError):
    """The gateway is reachable but no valid user session exists."""


class AmbiguousProfile(GatewayError):
    """More than one active provider profile exists and no selection was supplied."""


class DatasetUnavailable(ScreamingFaceError):
    """A gated benchmark cannot be loaded in the current environment."""


class FusionNotReady(ScreamingFaceError):
    """A fusion cannot run with the gateway's current models/connections."""

    def __init__(
        self,
        missing: dict[str, tuple[str, ...]],
        unavailable_models: tuple[str, ...] = (),
    ) -> None:
        self.missing_providers = tuple(sorted(missing))
        self.unavailable_models = unavailable_models
        lines = ["Fusion is not ready."]
        if missing:
            lines.append("Connect these providers:")
            for provider in self.missing_providers:
                lines.append(f"- {provider} — required by {', '.join(missing[provider])}")
        if unavailable_models:
            lines.append("These models are not available from AI Gateway:")
            lines.extend(f"- {model}" for model in unavailable_models)
        lines.extend(
            [
                "Run sf.setup(), connect the required providers, and retry.",
                "No benchmark data was loaded and no model calls were made.",
            ]
        )
        super().__init__("\n".join(lines))

    def _render_traceback_(self) -> list[str]:
        """Let IPython show the actionable failure without internal worker frames."""
        return [f"FusionNotReady: {self}"]


class ProviderCallError(ScreamingFaceError):
    """One model provider call failed without invalidating other panel answers."""

    def __init__(self, model: str, code: str, message: str) -> None:
        self.model = model
        self.code = code
        super().__init__(message)
