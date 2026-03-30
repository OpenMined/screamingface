"""ClaudeAdapter — translates between canonical messages and Anthropic Messages API format."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx

from screamingface.core.session import (
    CanonicalMessage,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
)

logger = logging.getLogger(__name__)

# Context window sizes per model family
_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4-0": 200_000,
    "claude-sonnet-4-2": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-haiku-3-5": 200_000,
}
_DEFAULT_CONTEXT = 200_000


class ClaudeAdapter:
    """Translates between CanonicalMessage and Anthropic Messages API format.

    Lives in claude_backend because it knows Anthropic-specific concerns.
    Used by the backend's session orchestration hooks.
    """

    provider_name: str = "anthropic"

    def __init__(
        self,
        upstream_url: str = "https://api.anthropic.com",
        api_key_resolver: Callable[[], str] | None = None,
    ) -> None:
        self._upstream_url = upstream_url.rstrip("/")
        self._api_key_resolver = api_key_resolver

    # ------------------------------------------------------------------
    # canonical → Anthropic
    # ------------------------------------------------------------------

    def to_provider_messages(
        self,
        messages: list[CanonicalMessage],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Convert canonical messages to Anthropic Messages API format.

        Returns {"messages": [...], "system": [...]} ready to merge into
        a MessagesRequest body.
        """
        system_blocks: list[dict[str, Any]] = []
        api_messages: list[dict[str, Any]] = []

        if system_prompt:
            system_blocks.append({"type": "text", "text": system_prompt})

        for msg in messages:
            if msg.role == "system":
                for block in msg.content:
                    system_blocks.append(self._canonical_to_api_block(block))
                continue

            # Determine whether to preserve thinking blocks:
            # Only preserve if this assistant message ended with tool_use
            preserve_thinking = (
                msg.role == "assistant" and msg.metadata.get("stop_reason") == "tool_use"
            )

            content_blocks: list[dict[str, Any]] = []
            for block in msg.content:
                if isinstance(block, ThinkingContent) and not preserve_thinking:
                    continue
                content_blocks.append(self._canonical_to_api_block(block))

            if content_blocks:
                api_messages.append(
                    {
                        "role": msg.role,
                        "content": content_blocks,
                    }
                )

        result: dict[str, Any] = {"messages": api_messages}
        if system_blocks:
            result["system"] = system_blocks
        return result

    def _canonical_to_api_block(self, block: Any) -> dict[str, Any]:
        """Convert a single canonical content block to Anthropic API dict."""
        if isinstance(block, TextContent):
            d: dict[str, Any] = {"type": "text", "text": block.text}
            if block.cache_hint == "persistent":
                d["cache_control"] = {"type": "ephemeral"}
            return d

        if isinstance(block, ThinkingContent):
            d = {"type": "thinking", "thinking": block.thinking}
            if block.signature:
                d["signature"] = block.signature
            return d

        if isinstance(block, ToolUseContent):
            return {
                "type": "tool_use",
                "id": block.tool_use_id,
                "name": block.name,
                "input": block.input,
            }

        if isinstance(block, ToolResultContent):
            return {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                "is_error": block.is_error,
            }

        if isinstance(block, ImageContent):
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": block.media_type,
                    "data": block.data,
                },
            }

        # Fallback: dump as-is
        return block.model_dump() if hasattr(block, "model_dump") else dict(block)

    # ------------------------------------------------------------------
    # Anthropic → canonical
    # ------------------------------------------------------------------

    def from_provider_response(
        self,
        response: dict[str, Any],
    ) -> list[CanonicalMessage]:
        """Parse an Anthropic MessagesResponse dict into canonical messages."""
        content_blocks = []
        thinking_signatures: list[str] = []

        for block in response.get("content", []):
            btype = block.get("type")

            if btype == "text":
                content_blocks.append(TextContent(text=block["text"]))

            elif btype == "tool_use":
                content_blocks.append(
                    ToolUseContent(
                        tool_use_id=block["id"],
                        name=block["name"],
                        input=block.get("input", {}),
                    )
                )

            elif btype == "thinking":
                sig = block.get("signature")
                content_blocks.append(
                    ThinkingContent(
                        thinking=block.get("thinking", ""),
                        signature=sig,
                    )
                )
                if sig:
                    thinking_signatures.append(sig)

            else:
                # Unknown block type — store as text with metadata
                content_blocks.append(
                    TextContent(
                        text=json.dumps(block),
                    )
                )

        metadata: dict[str, Any] = {}
        if response.get("stop_reason"):
            metadata["stop_reason"] = response["stop_reason"]
        if thinking_signatures:
            metadata["thinking_signatures"] = thinking_signatures

        usage = response.get("usage", {})
        token_count = usage.get("output_tokens")

        return [
            CanonicalMessage(
                role="assistant",
                content=content_blocks,
                provider="anthropic",
                model=response.get("model"),
                token_count=token_count,
                metadata=metadata,
            )
        ]

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    async def estimate_tokens(
        self,
        messages: list[CanonicalMessage],
        model: str = "claude-sonnet-4-20250514",
    ) -> int:
        """Estimate token count. Uses Anthropic's count_tokens API with fallback."""
        try:
            return await self._count_tokens_api(messages, model)
        except Exception:
            logger.debug("Token counting API unavailable, using heuristic", exc_info=True)
            provider_data = self.to_provider_messages(messages)
            return len(json.dumps(provider_data)) // 4

    async def _count_tokens_api(
        self,
        messages: list[CanonicalMessage],
        model: str,
    ) -> int:
        """Call Anthropic's POST /v1/messages/count_tokens endpoint."""
        if not self._api_key_resolver:
            raise RuntimeError("No API key resolver configured")

        provider_data = self.to_provider_messages(messages)
        body: dict[str, Any] = {
            "model": model,
            "messages": provider_data["messages"],
        }
        if "system" in provider_data:
            body["system"] = provider_data["system"]

        api_key = self._api_key_resolver()
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._upstream_url}/v1/messages/count_tokens",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()["input_tokens"]

    # ------------------------------------------------------------------
    # Context window
    # ------------------------------------------------------------------

    def max_context_tokens(self, model: str) -> int:
        """Return max context window size for a model."""
        for prefix, tokens in _CONTEXT_WINDOWS.items():
            if model.startswith(prefix):
                return tokens
        return _DEFAULT_CONTEXT

    # ------------------------------------------------------------------
    # Cache control hints
    # ------------------------------------------------------------------

    def cache_control_hints(
        self,
        messages: list[CanonicalMessage],
    ) -> list[dict[str, Any]]:
        """Compute prompt caching breakpoint positions.

        Returns a list of dicts describing where to place cache_control
        hints. Each has: message_index, block_index, cache_control.
        """
        hints: list[dict[str, Any]] = []
        cumulative_tokens = 0

        for i, msg in enumerate(messages):
            if msg.role == "system":
                # Always cache after system prompt
                hints.append(
                    {
                        "message_index": i,
                        "block_index": len(msg.content) - 1,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
                continue

            # Skip assistant messages in tool-use chains (don't break
            # thinking→tool_use pairs)
            if msg.role == "assistant" and msg.metadata.get("stop_reason") == "tool_use":
                cumulative_tokens += msg.token_count or 0
                continue

            cumulative_tokens += msg.token_count or 0

            # Place breakpoint every ~1000 tokens of stable history
            if cumulative_tokens >= 1000:
                hints.append(
                    {
                        "message_index": i,
                        "block_index": len(msg.content) - 1 if msg.content else 0,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
                cumulative_tokens = 0

        # Always place a breakpoint before the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "user":
                hint = {
                    "message_index": i,
                    "block_index": 0,
                    "cache_control": {"type": "ephemeral"},
                }
                if not hints or hints[-1]["message_index"] != i:
                    hints.append(hint)
                break

        return hints
