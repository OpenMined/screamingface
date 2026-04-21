"""Pydantic models for Ollama /api/chat request/response shapes.

These are typed for documentation and optional validation; the proxy itself
mutates request bodies as dicts to preserve forward-compatibility with
new Ollama fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class OllamaMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    images: list[str] | None = None
    tool_calls: list[dict[str, Any]] | None = None


class OllamaChatRequest(BaseModel):
    model: str
    messages: list[OllamaMessage]
    stream: bool = True
    options: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    format: str | dict[str, Any] | None = None
    keep_alive: str | int | None = None


class OllamaChatResponse(BaseModel):
    model: str
    created_at: str
    message: OllamaMessage
    done: bool
    done_reason: str | None = None
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None
