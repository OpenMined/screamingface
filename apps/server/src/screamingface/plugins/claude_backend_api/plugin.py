"""claude-backend-api plugin — direct Anthropic Messages API implementation.

Declares:

- ``depends = ["llm-base"]`` — needs the shared ABCs and credential store
- ``conflicts = ["claude-backend"]`` — mutually exclusive with the
  CLI-subprocess plugin. The SF plugin loader refuses to activate both
  at the same time; operators pick exactly one by listing it in the
  ``sf.json`` plugins array.

Exposes the same routes as ``claude-backend`` (``/claude/run``,
``/claude``, ``/claude/{profile_name}``) so existing url4 specs and
tests work unchanged. Only the implementation under the routes differs
— subprocess → direct httpx POST.

Settings mirror ``claude-backend`` field-for-field. Env prefix is
``SF_CLAUDE_BACKEND_API__`` (not ``SF_CLAUDE_BACKEND__``) so env-var
overrides for the two plugins stay independent. Per-field names
(``default_model``, ``default_effort``, etc.) are the same.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_backend_api.models import BackendProfile
from screamingface.plugins.claude_backend_api.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ClaudeBackendApiSettings(PluginSettings):
    """Settings for claude-backend-api.

    Mirrors ``ClaudeBackendSettings`` in all user-visible field names.
    CLI-only settings (``permission_mode``, ``dangerously_skip_permissions``)
    are accepted but silently ignored at request time, per the locked-in
    drop-in-compat decision in the plan.
    """

    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description=(
            "Default Claude model for requests that don't specify one. "
            "Falls back to 'claude-sonnet-4-6' if still unset at call time."
        ),
    )
    default_effort: str = Field(
        default="medium",
        description="Default effort level.",
    )
    interpreter_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
        description=("System prompt used by the /claude?q= url4 interpreter endpoint."),
    )
    timeout_seconds: float = Field(
        default=300.0,
        description="Default request timeout in seconds (httpx read timeout).",
    )
    max_budget_usd: float | None = Field(
        default=None,
        description=(
            "CLI-only budget cap. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend (no budget "
            "enforcement on this path)."
        ),
    )
    permission_mode: str | None = Field(
        default=None,
        description=(
            "CLI-only setting. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    dangerously_skip_permissions: bool = Field(
        default=False,
        description=(
            "CLI-only setting. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    profiles: dict[str, BackendProfile] = Field(
        default_factory=dict,
        description="Named pre-configured Claude execution profiles.",
    )
    default_profile: str = Field(
        default="default",
        description="Profile to use when none is specified. Must exist in profiles.",
    )

    @field_validator("profiles")
    @classmethod
    def _validate_profile_keys(cls, v: dict[str, BackendProfile]) -> dict[str, BackendProfile]:
        for key in v:
            if not _PROFILE_NAME_RE.match(key):
                msg = (
                    f"Invalid profile name {key!r}: must be lowercase "
                    "alphanumeric, hyphens, or underscores, starting with "
                    "a letter or digit."
                )
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_default_profile(self) -> ClaudeBackendApiSettings:
        if self.default_profile and self.profiles and self.default_profile not in self.profiles:
            msg = (
                f"default_profile {self.default_profile!r} not found in profiles. "
                f"Available: {list(self.profiles.keys())}"
            )
            raise ValueError(msg)
        return self


class ClaudeBackendApiPlugin(Plugin):
    name = "claude-backend-api"
    description = (
        "Direct Anthropic Messages API backend — drop-in replacement for "
        "claude-backend that uses OAuth from the Claude Code credential "
        "store instead of shelling out to the claude CLI. Same routes, "
        "same request/response shapes, same profile config."
    )
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = []
    # Registered for url4 backend-call dispatch via /claude()!<intent>.
    # The url4 resolver walks active plugins looking for one whose
    # backend_call_paths contains the target path and calls its
    # handle_backend_call method. This is how SF-79 Stage B wires fan-out
    # calls to the underlying llm-base Backend.
    backend_call_paths: list[str] = ["/claude"]
    settings_class = ClaudeBackendApiSettings

    def customize_schema(self, schema: dict) -> dict:
        settings: ClaudeBackendApiSettings = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = "/claude/"
        return schema

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(self.settings, app)  # type: ignore[arg-type]
        routes.add_router(self.name, router, prefix="")

    async def handle_backend_call(self, intent: str, *, sources: str = "", app: FastAPI) -> str:
        """Dispatch a url4 backend-call to the direct Anthropic API.

        Constructs a :class:`ClaudeBackendApiInterpreter` and delegates to
        its ``process(sources, intent)`` method — the same path the
        existing ``GET /claude?q=`` route uses. Reusing the interpreter
        means the backend-call dispatch inherits every behavior it already
        has (default model, system prompt, timeout, auth strategy).

        SF-89 context packing: when the backend call had non-empty parens
        (``/claude('What is quantum computing?')!Explain``), the *sources*
        argument carries the packed context text. The interpreter's
        ``process()`` method concatenates ``intent + "\\n\\n" + sources``
        so the LLM sees the context followed by the instruction.
        """
        # Lazy import to avoid a circular dependency at module load.
        from screamingface.plugins.claude_backend_api.interpreter import (
            ClaudeBackendApiInterpreter,
        )

        interpreter = ClaudeBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
        return await interpreter.process(sources=sources, intent=intent)
