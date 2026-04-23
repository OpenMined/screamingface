"""Adapter between CoreMessage lists and Ollama /api/chat wire format.

Ollama's native chat shape is flatter than Anthropic or OpenAI
Responses:

Request:
  - ``model`` — model name (e.g. "llama3.2:1b")
  - ``messages`` — list of ``{"role", "content"}`` where ``content`` is
    a plain string (no content-block arrays)
  - ``stream`` — phase 1 always sends ``false``
  - ``options`` — optional dict with ``num_predict`` (max tokens),
    ``temperature``, etc.
  - ``tools`` — optional list using the OpenAI function-tool schema

Response (non-streaming):
  - ``model`` — model name echoed back
  - ``created_at`` — ISO 8601 timestamp
  - ``message`` — ``{"role": "assistant", "content": "..."}``
  - ``done`` — always ``true`` for non-stream
  - ``done_reason`` — e.g. ``"stop"``
  - ``total_duration`` / ``load_duration`` / ``prompt_eval_count`` /
    ``prompt_eval_duration`` / ``eval_count`` / ``eval_duration`` —
    nanosecond timing + token counts

Phase 1 supports text-only conversation. Multimodal parts (images) and
tool-call round-trips are not implemented yet — non-text ContentParts
are silently dropped with a debug log.
"""

from __future__ import annotations

import logging
from typing import Any

from screamingface.plugins.llm_base.adapter_base import Adapter
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    ContentPart,
    CoreMessage,
    TextPart,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OllamaAdapter(Adapter):
    """CoreMessage ↔ Ollama /api/chat shape."""

    # ------------------------------------------------------------------
    # Outbound: CoreMessage → Ollama request body
    # ------------------------------------------------------------------

    def to_provider_format(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 16000,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        out_messages: list[dict[str, Any]] = []

        # Collect any explicit system prompt plus any role="system" CoreMessages
        # into a single leading system message (Ollama has no top-level system
        # field — it must live in messages[0]).
        system_chunks: list[str] = []
        if system:
            system_chunks.append(system)

        for msg in messages:
            if msg.role == "system":
                text = _flatten_content(msg.content)
                if text:
                    system_chunks.append(text)
                continue
            out_messages.append({"role": msg.role, "content": _flatten_content(msg.content)})

        if system_chunks:
            out_messages.insert(0, {"role": "system", "content": "\n\n".join(system_chunks)})

        body: dict[str, Any] = {
            "model": model,
            "messages": out_messages,
            "stream": False,
        }

        options: dict[str, Any] = {}
        if max_tokens:
            options["num_predict"] = max_tokens
        if temperature is not None:
            options["temperature"] = temperature
        if options:
            body["options"] = options

        if tools:
            body["tools"] = [_tool_definition_to_ollama(t) for t in tools]

        return body

    # ------------------------------------------------------------------
    # Inbound: Ollama response → CoreMessage
    # ------------------------------------------------------------------

    def from_provider_response(self, data: dict[str, Any]) -> CoreMessage:
        if not isinstance(data, dict):
            raise AdapterError("Ollama response is not a dict")

        msg = data.get("message")
        if not isinstance(msg, dict):
            raise AdapterError("Ollama response missing 'message' field")

        content = msg.get("content", "") or ""
        if not isinstance(content, str):
            raise AdapterError(
                f"Ollama response message.content is not a string (got {type(content).__name__})"
            )

        metadata_keys = (
            "model",
            "created_at",
            "done",
            "done_reason",
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
        )
        provider_metadata: dict[str, Any] = {}
        for key in metadata_keys:
            if key in data and data[key] is not None:
                provider_metadata[f"ollama.{key}"] = data[key]

        return CoreMessage(
            role="assistant",
            content=[TextPart(text=content)],
            provider_metadata=provider_metadata or None,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_content(content: str | list[ContentPart]) -> str:
    """Reduce a CoreMessage ``content`` value to a single string.

    Ollama's wire format has no content-block arrays — each message
    carries a plain string. Multi-part content is concatenated; non-text
    parts (images, tool_use, tool_result) are silently dropped with a
    debug log because phase 1 doesn't support them.
    """
    if isinstance(content, str):
        return content
    chunks: list[str] = []
    for part in content:
        if isinstance(part, TextPart):
            chunks.append(part.text)
        else:
            logger.debug("OllamaAdapter dropping unsupported content part: %s", type(part).__name__)
    return "".join(chunks)


def _tool_definition_to_ollama(tool: ToolDefinition) -> dict[str, Any]:
    """Map a :class:`ToolDefinition` to Ollama's (OpenAI-style) tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }
