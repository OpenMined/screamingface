"""Adapter between CoreMessage lists and OpenAI Responses API shape.

The Codex CLI uses the Responses API (``/v1/responses``), not Chat
Completions. The Responses API has a different request/response shape:

Request:
  - ``model`` -- model name
  - ``input`` -- a string or list of messages (each with role + content)
  - ``instructions`` -- system prompt (top-level, not in messages)
  - ``max_output_tokens`` -- max tokens to generate
  - ``temperature`` -- sampling temperature
  - ``tools`` -- function definitions (same wrapper as Chat Completions)

Response:
  - ``id`` -- response ID
  - ``output`` -- list of output items
  - ``output[].type`` -- ``"message"`` for text responses
  - ``output[].content`` -- list of content parts
  - ``output[].content[].type`` -- ``"output_text"`` for text
  - ``output[].content[].text`` -- the actual text
  - ``usage`` -- token counts
"""

from __future__ import annotations

import json
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


class OpenAIResponsesAdapter(Adapter):
    """Adapter between CoreMessage and OpenAI Responses API shape."""

    # ------------------------------------------------------------------
    # Outbound: CoreMessage -> OpenAI Responses API request body
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
        """Produce an OpenAI Responses API request body."""
        body: dict[str, Any] = {
            "model": model,
            "max_output_tokens": max_tokens,
        }

        if temperature is not None:
            body["temperature"] = temperature

        # Collect system content -> instructions field
        system_chunks: list[str] = []
        if system:
            system_chunks.append(system)

        input_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                text = self._extract_system_text(msg)
                if text:
                    system_chunks.append(text)
            else:
                converted = self._message_to_responses(msg)
                if converted is not None:
                    if isinstance(converted, list):
                        input_messages.extend(converted)
                    else:
                        input_messages.append(converted)

        if system_chunks:
            body["instructions"] = "\n\n".join(system_chunks)

        # For simple single-message user input, use string shorthand
        if (
            len(input_messages) == 1
            and input_messages[0].get("role") == "user"
            and isinstance(input_messages[0].get("content"), str)
        ):
            body["input"] = input_messages[0]["content"]
        else:
            body["input"] = input_messages

        if tools:
            body["tools"] = [self._tool_to_openai(t) for t in tools]

        return body

    # ------------------------------------------------------------------
    # Inbound: OpenAI Responses API response -> CoreMessage
    # ------------------------------------------------------------------

    def from_provider_response(self, data: dict[str, Any]) -> CoreMessage:
        """Parse a successful OpenAI Responses API 200 response.

        The response shape is::

            {
              "id": "resp_...",
              "object": "response",
              "output": [
                {
                  "type": "message",
                  "role": "assistant",
                  "content": [
                    {"type": "output_text", "text": "..."}
                  ]
                }
              ],
              "usage": {...},
              "model": "..."
            }
        """
        if not isinstance(data, dict):
            raise AdapterError(f"OpenAI response is not a dict: got {type(data).__name__}")

        output = data.get("output")
        if not isinstance(output, list) or len(output) == 0:
            raise AdapterError("OpenAI response missing or empty 'output' field")

        parts: list[Any] = []

        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")

            if item_type == "message":
                content_list = item.get("content", [])
                for block in content_list:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "output_text":
                        parts.append(TextPart(text=block.get("text", "")))
                    elif btype == "refusal":
                        parts.append(TextPart(text=f"[Refused: {block.get('refusal', '')}]"))

            elif item_type == "function_call":
                arguments_str = item.get("arguments", "{}")
                try:
                    arguments = json.loads(arguments_str)
                except (json.JSONDecodeError, TypeError):
                    arguments = {"raw": arguments_str}
                parts.append(
                    ToolCallPart(
                        tool_call_id=item.get("call_id", item.get("id", "")),
                        tool_name=item.get("name", ""),
                        input=arguments,
                    )
                )

        # Provider metadata
        provider_metadata: dict[str, Any] = {}
        for key in ("id", "model", "usage"):
            if key in data:
                provider_metadata[f"openai.{key}"] = data[key]
        status = data.get("status")
        if status:
            provider_metadata["openai.status"] = status

        return CoreMessage(
            role="assistant",
            content=parts if parts else "",
            provider_metadata=provider_metadata or None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_system_text(self, msg: CoreMessage) -> str:
        """Flatten a system CoreMessage into a plain string."""
        if isinstance(msg.content, str):
            return msg.content
        chunks = []
        for part in msg.content:
            if isinstance(part, TextPart):
                chunks.append(part.text)
        return "\n\n".join(chunks)

    def _message_to_responses(
        self, msg: CoreMessage
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Translate a single non-system CoreMessage to Responses API shape."""
        if isinstance(msg.content, str):
            return {"role": msg.role, "content": msg.content}

        # Tool results become function_call_output items
        if msg.role in ("tool", "user"):
            tool_results = [p for p in msg.content if isinstance(p, ToolResultPart)]
            if tool_results:
                items: list[dict[str, Any]] = []
                other_parts = [p for p in msg.content if not isinstance(p, ToolResultPart)]
                if other_parts:
                    text = self._parts_to_text(other_parts)
                    if text:
                        items.append({"role": "user", "content": text})
                for tr in tool_results:
                    output = tr.output if isinstance(tr.output, str) else json.dumps(tr.output)
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": tr.tool_call_id,
                            "output": output,
                        }
                    )
                return items if items else None

        # Assistant message with tool calls
        if msg.role == "assistant":
            items = []
            text_parts = []
            for part in msg.content:
                if isinstance(part, TextPart):
                    text_parts.append(part.text)
                elif isinstance(part, ToolCallPart):
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": part.tool_call_id,
                            "name": part.tool_name,
                            "arguments": json.dumps(part.input),
                        }
                    )
            # Text content goes as a message item
            content_text = "".join(text_parts)
            if content_text:
                items.insert(0, {"role": "assistant", "content": content_text})
            return items if items else None

        # Generic user message
        text = self._parts_to_text(msg.content)
        return {"role": msg.role, "content": text} if text else None

    def _parts_to_text(self, parts: list) -> str:
        """Extract concatenated text from a list of content parts."""
        chunks = []
        for part in parts:
            if isinstance(part, TextPart):
                chunks.append(part.text)
        return "".join(chunks)

    def _tool_to_openai(self, tool: ToolDefinition) -> dict[str, Any]:
        """Translate a ToolDefinition to OpenAI's function-wrapped shape."""
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }
