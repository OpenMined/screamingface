"""Request and response schemas for the claude-cli plugin."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field

from screamingface.models import AliasedModel


def _alias(short: str) -> dict:
    """Helper to create validation + serialization alias config for a field."""
    return {
        "validation_alias": AliasChoices(short),
        "serialization_alias": short,
    }


class FileInput(AliasedModel):
    filename: str = Field(**_alias("fn"))
    content: str = Field(**_alias("c"))


class ClaudeRunRequest(AliasedModel):
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


class ClaudeRunResponse(AliasedModel):
    exit_code: int = Field(**_alias("ec"))
    stdout: str = Field(**_alias("so"))
    stderr: str = Field(**_alias("se"))
    duration_seconds: float = Field(**_alias("ds"))
    result: dict | list | str | None = Field(default=None, **_alias("r"))
