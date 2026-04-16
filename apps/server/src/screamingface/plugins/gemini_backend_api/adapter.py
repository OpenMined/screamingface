"""Adapter between CoreMessage lists and Google AI Gemini API shape.

Supports two response formats:

1. Standard API (generativelanguage.googleapis.com):
   - candidates: [{content: {parts: [{text: "..."}], role: "model"}, finishReason}]
   - usageMetadata: {promptTokenCount, candidatesTokenCount, totalTokenCount}

2. Code Assist API (cloudcode-pa.googleapis.com):
   - response: {candidates: [...], usageMetadata: {...}}
   - traceId: "..."
   The backend unwraps the envelope before passing to this adapter.

Request body (standard format, used by both paths):
  - contents: [{role: "user"|"model", parts: [{text: "..."}]}]
  - systemInstruction: {parts: [{text: "..."}]}
  - generationConfig: {maxOutputTokens, temperature}
  - tools: [{functionDeclarations: [...]}]
"""

from __future__ import annotations

from typing import Any

from screamingface.plugins.llm_base.adapter_base import Adapter
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)


class GeminiAdapter(Adapter):
    """Adapter between CoreMessage and Google AI Gemini API shape."""

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
        body: dict[str, Any] = {
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        if temperature is not None:
            body["generationConfig"]["temperature"] = temperature

        # System prompt -> systemInstruction
        system_chunks: list[str] = []
        if system:
            system_chunks.append(system)

        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                text = self._extract_text(msg)
                if text:
                    system_chunks.append(text)
            else:
                converted = self._message_to_gemini(msg)
                if converted:
                    contents.append(converted)

        if system_chunks:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_chunks)}]}

        body["contents"] = contents

        if tools:
            body["tools"] = [{"functionDeclarations": [self._tool_to_gemini(t) for t in tools]}]

        # Model is passed in the URL, not the body, but we store it
        # for the backend to use when constructing the URL.
        body["_model"] = model

        return body

    def from_provider_response(self, data: dict[str, Any]) -> CoreMessage:
        if not isinstance(data, dict):
            raise AdapterError(f"Gemini response is not a dict: got {type(data).__name__}")

        candidates = data.get("candidates")
        if not isinstance(candidates, list) or len(candidates) == 0:
            raise AdapterError("Gemini response missing or empty 'candidates' field")

        candidate = candidates[0]
        content = candidate.get("content", {})
        raw_parts = content.get("parts", [])

        parts: list[Any] = []
        for part in raw_parts:
            if not isinstance(part, dict):
                continue
            if "text" in part:
                parts.append(TextPart(text=part["text"]))
            elif "functionCall" in part:
                fc = part["functionCall"]
                parts.append(
                    ToolCallPart(
                        tool_call_id=fc.get("id", ""),
                        tool_name=fc.get("name", ""),
                        input=fc.get("args", {}),
                    )
                )

        # Provider metadata
        provider_metadata: dict[str, Any] = {}
        usage = data.get("usageMetadata")
        if usage:
            provider_metadata["gemini.usage"] = usage
        finish_reason = candidate.get("finishReason")
        if finish_reason:
            provider_metadata["gemini.finish_reason"] = finish_reason

        return CoreMessage(
            role="assistant",
            content=parts if parts else "",
            provider_metadata=provider_metadata or None,
        )

    def _extract_text(self, msg: CoreMessage) -> str:
        if isinstance(msg.content, str):
            return msg.content
        return "\n\n".join(p.text for p in msg.content if isinstance(p, TextPart))

    def _message_to_gemini(self, msg: CoreMessage) -> dict[str, Any] | None:
        # Gemini uses "user" and "model" roles
        role = "model" if msg.role == "assistant" else "user"

        if isinstance(msg.content, str):
            return {"role": role, "parts": [{"text": msg.content}]}

        parts: list[dict[str, Any]] = []
        for part in msg.content:
            if isinstance(part, TextPart):
                parts.append({"text": part.text})
            elif isinstance(part, ToolCallPart):
                parts.append(
                    {
                        "functionCall": {
                            "name": part.tool_name,
                            "args": part.input,
                        }
                    }
                )
            elif isinstance(part, ToolResultPart):
                output = part.output if isinstance(part.output, dict) else {"result": part.output}
                parts.append(
                    {
                        "functionResponse": {
                            "name": part.tool_name,
                            "response": output,
                        }
                    }
                )

        return {"role": role, "parts": parts} if parts else None

    def _tool_to_gemini(self, tool: ToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }
