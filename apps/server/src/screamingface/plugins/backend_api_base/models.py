"""Request/response/profile shapes shared by every *_backend_api plugin.

The ensemble fan-out system sends byte-identical HTTP requests to every
direct-API backend (claude, codex, gemini, ollama, …). These models are
that wire contract.

Legacy ``Claude*`` aliases are re-exported for one release so existing
``sf.json`` profiles and callers keep working. New code should use the
unprefixed names.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from screamingface.models import AliasedModel


class BackendProfile(BaseModel):
    """A named pre-configured backend execution endpoint."""

    context: str | None = Field(
        default=None,
        description="URL4 expression for context (resolved at request time).",
    )
    system_prompt: str | None = Field(default=None, description="System prompt.")
    append_system_prompt: str | None = Field(
        default=None, description="Text appended to system prompt."
    )
    model: str | None = Field(default=None, description="Model override.")
    output_format: Literal["text", "json", "stream-json"] | None = Field(
        default=None, description="Output format."
    )
    json_schema: dict | None = Field(default=None, description="JSON schema for structured output.")
    max_budget_usd: float | None = Field(default=None, description="Budget cap in USD.")
    effort: Literal["low", "medium", "high", "max"] | None = Field(
        default=None, description="Effort level."
    )
    tools: list[str] | None = Field(default=None, description="Tools to enable.")
    allowed_tools: list[str] | None = Field(default=None, description="Allowed tools.")
    disallowed_tools: list[str] | None = Field(default=None, description="Disallowed tools.")
    mcp_config: str | None = Field(default=None, description="Path to MCP config.")
    permission_mode: str | None = Field(default=None, description="Permission mode.")
    add_dirs: list[str] | None = Field(default=None, description="Additional directories.")
    fallback_model: str | None = Field(default=None, description="Fallback model.")
    dangerously_skip_permissions: bool = Field(default=False)
    no_session_persistence: bool = Field(default=True)
    timeout_seconds: float | None = Field(default=None, description="Timeout override.")


def _alias(short: str) -> dict:
    return {
        "validation_alias": AliasChoices(short),
        "serialization_alias": short,
    }


class FileInput(AliasedModel):
    filename: str = Field(**_alias("fn"))
    content: str = Field(**_alias("c"))


class RunRequest(AliasedModel):
    prompt: str = Field(**_alias("p"))
    model: str | None = Field(default=None, **_alias("m"))
    system_prompt: str | None = Field(default=None, **_alias("sp"))
    append_system_prompt: str | None = Field(default=None, **_alias("asp"))
    output_format: Literal["text", "json", "stream-json"] | None = Field(
        default=None, **_alias("of")
    )
    json_schema: dict | None = Field(default=None, **_alias("js"))
    max_budget_usd: float | None = Field(default=None, **_alias("mb"))
    effort: Literal["low", "medium", "high", "max"] | None = Field(default=None, **_alias("e"))
    tools: list[str] | None = Field(default=None, **_alias("t"))
    allowed_tools: list[str] | None = Field(default=None, **_alias("at"))
    disallowed_tools: list[str] | None = Field(default=None, **_alias("dt"))
    mcp_config: str | None = Field(default=None, **_alias("mc"))
    permission_mode: str | None = Field(default=None, **_alias("pm"))
    add_dirs: list[str] | None = Field(default=None, **_alias("ad"))
    files: list[FileInput] | None = Field(default=None, **_alias("f"))
    fallback_model: str | None = Field(default=None, **_alias("fm"))
    dangerously_skip_permissions: bool = Field(default=False, **_alias("dsp"))
    no_session_persistence: bool = Field(default=True, **_alias("nsp"))
    timeout_seconds: float | None = Field(default=None, **_alias("ts"))


class RunResponse(AliasedModel):
    exit_code: int = Field(**_alias("ec"))
    stdout: str = Field(**_alias("so"))
    stderr: str = Field(**_alias("se"))
    duration_seconds: float = Field(**_alias("ds"))
    result: dict | list | str | None = Field(default=None, **_alias("r"))


# Legacy aliases — kept for one release to avoid churning every call
# site in a single PR. New code should import the unprefixed names.
ClaudeProfile = BackendProfile
ClaudeRunRequest = RunRequest
ClaudeRunResponse = RunResponse


__all__ = [
    "BackendProfile",
    "FileInput",
    "RunRequest",
    "RunResponse",
    "ClaudeProfile",
    "ClaudeRunRequest",
    "ClaudeRunResponse",
]
