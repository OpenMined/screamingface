"""Adapter between CoreMessage lists and Anthropic Messages API shape.

Phase 1 scope — handles the message-content block types we actually use:

- ``TextPart`` ↔ Anthropic text block (``{"type": "text", "text": "..."}``)
- ``ToolCallPart`` ↔ Anthropic ``tool_use`` block
- ``ToolResultPart`` ↔ Anthropic ``tool_result`` block
- ``ReasoningPart`` → Anthropic ``thinking`` block (one-way, best effort)

Not yet handled (Phase 3 follow-ups):

- ``ImagePart`` — requires base64 encoding + media_type header
  detection. Phase 3.
- ``ReasoningPart`` inbound — Anthropic's thinking blocks carry
  signatures that we preserve via ``provider_metadata`` but don't
  currently produce from our own response parser.
- Anthropic's ``server_tool_use`` / ``*_tool_result`` variants — these
  come from Anthropic's server-side tools (web search, code exec,
  etc.). Phase 3.
- Tools with ``input_schema`` containing non-trivial JSON Schema
  features. The naive passthrough works for the common case.

Also performs the **orphan repair pass**: strips assistant ``tool_use``
blocks whose matching user ``tool_result`` is absent, and vice versa.
Anthropic's API enforces strict pairing and returns 400 when a
``tool_use`` has no matching ``tool_result`` in a subsequent user
message.
"""

from __future__ import annotations

import hashlib
from typing import Any

from screamingface.plugins.llm_base.adapter_base import (
    Adapter,
    collect_provider_metadata,
    extract_system_text,
)
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)

# Billing fingerprint constants — must match the Claude Code CLI's
# src/utils/fingerprint.ts to route requests to the CLI rate limit pool.
_FINGERPRINT_SALT = "59cf53e54c78"
_CC_VERSION = "2.1.104"


class AnthropicAdapter(Adapter):
    """Hand-rolled adapter between CoreMessage and Anthropic Messages API shape.

    No external dependencies beyond ``llm_base``. See the module docstring
    for the Phase 1 scope and known limitations.
    """

    # ------------------------------------------------------------------
    # Outbound: CoreMessage → Anthropic request body
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
        """Produce an Anthropic Messages API request body.

        Separates the ``system`` field from the ``messages`` array (Anthropic
        requires system at the top level, not as a role). Drops any
        ``CoreMessage`` with ``role == "system"`` after merging its content
        into the top-level system string.

        Applies the orphan-repair pass before emitting.
        """
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
        }

        if temperature is not None:
            body["temperature"] = temperature

        # Collect system content: explicit system arg + any "system"-role
        # messages (merged in order with newline separators).
        system_chunks: list[str] = []
        if system:
            system_chunks.append(system)

        non_system_messages: list[CoreMessage] = []
        for msg in messages:
            if msg.role == "system":
                text = self._extract_system_text(msg)
                if text:
                    system_chunks.append(text)
            else:
                non_system_messages.append(msg)

        # Build the system array with billing header prepended.
        # The billing header routes requests to the Claude Code rate
        # limit pool (same pool the CLI uses).
        first_user_text = self._extract_first_user_text(non_system_messages)
        billing_block = _build_billing_header(first_user_text)
        system_blocks: list[dict[str, Any]] = [{"type": "text", "text": billing_block}]
        for chunk in system_chunks:
            system_blocks.append({"type": "text", "text": chunk})
        body["system"] = system_blocks

        # Translate each non-system message
        anthropic_messages = [self._message_to_anthropic(m) for m in non_system_messages]

        # Orphan-repair pass — strip unpaired tool_use / tool_result
        body["messages"] = self._repair_tool_pairs(anthropic_messages)

        if tools:
            body["tools"] = [self._tool_to_anthropic(t) for t in tools]

        return body

    # ------------------------------------------------------------------
    # Inbound: Anthropic response → CoreMessage
    # ------------------------------------------------------------------

    def from_provider_response(self, data: dict[str, Any]) -> CoreMessage:
        """Parse a successful Anthropic /v1/messages 200 response.

        The response shape is::

            {
              "id": "msg_...",
              "type": "message",
              "role": "assistant",
              "content": [
                {"type": "text", "text": "..."},
                {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
                ...
              ],
              "model": "...",
              "stop_reason": "...",
              "usage": {...}
            }
        """
        if not isinstance(data, dict):
            raise AdapterError(f"Anthropic response is not a dict: got {type(data).__name__}")

        if data.get("type") != "message":
            raise AdapterError(
                f"Anthropic response.type is {data.get('type')!r}, expected 'message'"
            )

        role = data.get("role", "assistant")
        if role not in ("assistant",):
            raise AdapterError(f"Anthropic response.role is {role!r}, expected 'assistant'")

        raw_content = data.get("content", [])
        if not isinstance(raw_content, list):
            raise AdapterError(
                f"Anthropic response.content is not a list: got {type(raw_content).__name__}"
            )

        parts: list[Any] = []
        for block in raw_content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(TextPart(text=block.get("text", "")))
            elif btype == "tool_use":
                parts.append(
                    ToolCallPart(
                        tool_call_id=block.get("id", ""),
                        tool_name=block.get("name", ""),
                        input=block.get("input", {}) or {},
                    )
                )
            elif btype == "thinking":
                parts.append(
                    ReasoningPart(
                        text=block.get("thinking", ""),
                        signature=block.get("signature"),
                    )
                )
            # Unknown block types are dropped silently. Phase 3 will
            # handle server_tool_use / *_tool_result variants.

        # Carry over the Anthropic-level metadata as provider_metadata on
        # the returned message. Useful for observability downstream.
        provider_metadata = collect_provider_metadata(
            data,
            ("id", "model", "stop_reason", "stop_sequence", "usage"),
            prefix="anthropic",
        )

        return CoreMessage(
            role="assistant",
            content=parts,
            provider_metadata=provider_metadata or None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_first_user_text(messages: list[CoreMessage]) -> str:
        """Get the text of the first user message for fingerprinting."""
        for msg in messages:
            if msg.role != "user":
                continue
            if isinstance(msg.content, str):
                return msg.content
            for part in msg.content:
                if isinstance(part, TextPart):
                    return part.text
        return ""

    @staticmethod
    def _extract_system_text(msg: CoreMessage) -> str:
        """Flatten a system CoreMessage into a plain string."""
        return extract_system_text(msg.content) or ""

    def _message_to_anthropic(self, msg: CoreMessage) -> dict[str, Any]:
        """Translate a single non-system CoreMessage to Anthropic shape."""
        # Anthropic roles: user or assistant only (no "tool" role; tool
        # results go inside user messages with tool_result blocks).
        role = msg.role
        if role == "tool":
            role = "user"

        if isinstance(msg.content, str):
            return {
                "role": role,
                "content": [{"type": "text", "text": msg.content}],
            }

        blocks: list[dict[str, Any]] = []
        for part in msg.content:
            block = self._part_to_anthropic(part)
            if block is not None:
                blocks.append(block)

        return {"role": role, "content": blocks}

    def _part_to_anthropic(self, part: Any) -> dict[str, Any] | None:
        """Translate a single content part to its Anthropic block shape.

        Unknown part types return None (skipped). Known types map as:

        - TextPart → {"type": "text", "text": ...}
        - ToolCallPart → {"type": "tool_use", "id": ..., "name": ..., "input": ...}
        - ToolResultPart → {"type": "tool_result", "tool_use_id": ..., "content": ...}
        - ReasoningPart → {"type": "thinking", "thinking": ..., "signature": ...}
        - ImagePart → NotImplemented (Phase 3)
        """
        if isinstance(part, TextPart):
            return {"type": "text", "text": part.text}
        if isinstance(part, ToolCallPart):
            return {
                "type": "tool_use",
                "id": part.tool_call_id,
                "name": part.tool_name,
                "input": part.input,
            }
        if isinstance(part, ToolResultPart):
            # Anthropic tool_result content can be a string or a list of
            # content blocks. We send strings for simplicity; if the
            # output is a dict we JSON-encode it.
            import json as _json

            if isinstance(part.output, str):
                content: Any = part.output
            else:
                content = _json.dumps(part.output)
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": part.tool_call_id,
                "content": content,
            }
            if part.is_error:
                block["is_error"] = True
            return block
        if isinstance(part, ReasoningPart):
            block = {"type": "thinking", "thinking": part.text}
            if part.signature is not None:
                block["signature"] = part.signature
            return block
        # ImagePart and any unknown types: drop (Phase 3 handles images)
        return None

    def _tool_to_anthropic(self, tool: ToolDefinition) -> dict[str, Any]:
        """Translate a ToolDefinition to Anthropic's tool shape."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    def _repair_tool_pairs(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip orphaned tool_use / tool_result blocks.

        Anthropic's API rejects requests where an assistant ``tool_use``
        has no matching user ``tool_result`` in a subsequent message
        (and vice versa). This pass removes such orphans and drops any
        message whose content list becomes empty as a result.

        Algorithm:
          1. Collect the set of tool_use IDs from assistant blocks.
          2. Collect the set of tool_use_ids referenced by user
             tool_result blocks.
          3. Valid IDs = intersection of the two sets.
          4. Walk messages; for each block, keep it if it's not
             tool-related, or its ID is in the valid set.
          5. Drop messages whose content becomes empty.
          6. Preserve order and all non-tool content.
        """
        use_ids: set[str] = set()
        result_ids: set[str] = set()

        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use" and msg.get("role") == "assistant":
                    if "id" in block:
                        use_ids.add(block["id"])
                elif btype == "tool_result" and msg.get("role") == "user":
                    if "tool_use_id" in block:
                        result_ids.add(block["tool_use_id"])

        valid = use_ids & result_ids

        repaired: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                repaired.append(msg)
                continue

            new_content: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    new_content.append(block)
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    if block.get("id") in valid:
                        new_content.append(block)
                    # else: orphan — drop
                elif btype == "tool_result":
                    if block.get("tool_use_id") in valid:
                        new_content.append(block)
                    # else: orphan — drop
                else:
                    new_content.append(block)

            if new_content:
                repaired.append({"role": msg["role"], "content": new_content})
            # else: message became empty, drop it

        return repaired


def _compute_fingerprint(first_user_text: str) -> str:
    """Compute the 3-char hex fingerprint matching Claude Code CLI.

    Takes characters at positions [4, 7, 20] from the first user message,
    concatenates with salt and CLI version, returns first 3 hex chars of SHA256.
    """
    chars = "".join(first_user_text[i] if i < len(first_user_text) else "0" for i in [4, 7, 20])
    raw = f"{_FINGERPRINT_SALT}{chars}{_CC_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:3]


def _build_billing_header(first_user_text: str) -> str:
    """Build the billing header string that routes to the CLI rate limit pool.

    Injected as the first system prompt block so Anthropic's backend
    identifies the request as a Claude Code CLI call.
    """
    fp = _compute_fingerprint(first_user_text)
    return (
        f"x-anthropic-billing-header: cc_version={_CC_VERSION}.{fp}; cc_entrypoint=cli; cch={fp};"
    )
