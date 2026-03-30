"""Tests for ClaudeAdapter — canonical ↔ Anthropic Messages API translation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from screamingface.core.session import (
    CanonicalMessage,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
)
from screamingface.plugins.claude.session_adapter import ClaudeAdapter


@pytest.fixture
def adapter() -> ClaudeAdapter:
    return ClaudeAdapter(upstream_url="https://api.anthropic.com")


# ---------------------------------------------------------------------------
# to_provider_messages
# ---------------------------------------------------------------------------


class TestToProviderMessages:
    def test_simple_text_conversation(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="user", content=[TextContent(text="Hello")]),
            CanonicalMessage(role="assistant", content=[TextContent(text="Hi!")]),
            CanonicalMessage(role="user", content=[TextContent(text="How are you?")]),
        ]
        result = adapter.to_provider_messages(messages)
        assert len(result["messages"]) == 3
        assert result["messages"][0] == {
            "role": "user",
            "content": [{"type": "text", "text": "Hello"}],
        }
        assert result["messages"][1] == {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi!"}],
        }
        assert "system" not in result

    def test_system_messages_extracted(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="system", content=[TextContent(text="Be helpful")]),
            CanonicalMessage(role="user", content=[TextContent(text="Hello")]),
        ]
        result = adapter.to_provider_messages(messages)
        assert result["system"] == [{"type": "text", "text": "Be helpful"}]
        assert len(result["messages"]) == 1

    def test_system_prompt_parameter(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="user", content=[TextContent(text="Hello")]),
        ]
        result = adapter.to_provider_messages(messages, system_prompt="Be concise")
        assert result["system"][0] == {"type": "text", "text": "Be concise"}

    def test_system_prompt_plus_system_messages(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="system", content=[TextContent(text="Rule 1")]),
            CanonicalMessage(role="user", content=[TextContent(text="Hello")]),
        ]
        result = adapter.to_provider_messages(messages, system_prompt="Be concise")
        assert len(result["system"]) == 2
        assert result["system"][0]["text"] == "Be concise"
        assert result["system"][1]["text"] == "Rule 1"

    def test_thinking_blocks_stripped_on_end_turn(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(
                role="assistant",
                content=[
                    ThinkingContent(thinking="reasoning...", signature="sig1"),
                    TextContent(text="Final answer"),
                ],
                metadata={"stop_reason": "end_turn"},
            ),
        ]
        result = adapter.to_provider_messages(messages)
        # Thinking block should be stripped
        assert len(result["messages"][0]["content"]) == 1
        assert result["messages"][0]["content"][0]["type"] == "text"

    def test_thinking_blocks_preserved_on_tool_use(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(
                role="assistant",
                content=[
                    ThinkingContent(thinking="reasoning...", signature="sig1"),
                    ToolUseContent(tool_use_id="tu_1", name="search", input={"q": "test"}),
                ],
                metadata={"stop_reason": "tool_use"},
            ),
        ]
        result = adapter.to_provider_messages(messages)
        assert len(result["messages"][0]["content"]) == 2
        assert result["messages"][0]["content"][0]["type"] == "thinking"
        assert result["messages"][0]["content"][0]["signature"] == "sig1"

    def test_cache_hint_mapped(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(
                role="user",
                content=[TextContent(text="cached", cache_hint="persistent")],
            ),
        ]
        result = adapter.to_provider_messages(messages)
        block = result["messages"][0]["content"][0]
        assert block["cache_control"] == {"type": "ephemeral"}

    def test_tool_use_and_result(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(
                role="assistant",
                content=[
                    ToolUseContent(tool_use_id="tu_1", name="get_weather", input={"city": "NYC"})
                ],
                metadata={"stop_reason": "tool_use"},
            ),
            CanonicalMessage(
                role="user",
                content=[ToolResultContent(tool_use_id="tu_1", content="Sunny, 72F")],
            ),
        ]
        result = adapter.to_provider_messages(messages)
        assert result["messages"][0]["content"][0]["type"] == "tool_use"
        assert result["messages"][0]["content"][0]["id"] == "tu_1"
        assert result["messages"][1]["content"][0]["type"] == "tool_result"
        assert result["messages"][1]["content"][0]["tool_use_id"] == "tu_1"

    def test_image_block(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(
                role="user",
                content=[ImageContent(media_type="image/png", data="iVBOR...")],
            ),
        ]
        result = adapter.to_provider_messages(messages)
        block = result["messages"][0]["content"][0]
        assert block["type"] == "image"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "image/png"

    def test_empty_messages(self, adapter: ClaudeAdapter) -> None:
        result = adapter.to_provider_messages([])
        assert result["messages"] == []
        assert "system" not in result


# ---------------------------------------------------------------------------
# from_provider_response
# ---------------------------------------------------------------------------


class TestFromProviderResponse:
    def test_text_response(self, adapter: ClaudeAdapter) -> None:
        response = {
            "id": "msg_abc",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello!"}],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = adapter.from_provider_response(response)
        assert len(result) == 1
        msg = result[0]
        assert msg.role == "assistant"
        assert msg.provider == "anthropic"
        assert msg.model == "claude-sonnet-4-20250514"
        assert msg.token_count == 5
        assert msg.metadata["stop_reason"] == "end_turn"
        assert isinstance(msg.content[0], TextContent)
        assert msg.content[0].text == "Hello!"

    def test_tool_use_with_thinking(self, adapter: ClaudeAdapter) -> None:
        response = {
            "content": [
                {"type": "thinking", "thinking": "I should search...", "signature": "sig_abc"},
                {"type": "tool_use", "id": "tu_1", "name": "search", "input": {"q": "test"}},
            ],
            "model": "claude-opus-4-20250514",
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        result = adapter.from_provider_response(response)
        msg = result[0]
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], ThinkingContent)
        assert msg.content[0].signature == "sig_abc"
        assert isinstance(msg.content[1], ToolUseContent)
        assert msg.metadata["stop_reason"] == "tool_use"
        assert msg.metadata["thinking_signatures"] == ["sig_abc"]

    def test_empty_content(self, adapter: ClaudeAdapter) -> None:
        response = {
            "content": [],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        result = adapter.from_provider_response(response)
        assert len(result) == 1
        assert result[0].content == []


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    @pytest.mark.anyio
    async def test_fallback_heuristic(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="user", content=[TextContent(text="Hello world")]),
        ]
        # No API key resolver → falls back to heuristic
        count = await adapter.estimate_tokens(messages)
        assert count > 0

    @pytest.mark.anyio
    async def test_api_call(self) -> None:
        adapter = ClaudeAdapter(
            upstream_url="https://api.anthropic.com",
            api_key_resolver=lambda: "test-key",
        )
        messages = [
            CanonicalMessage(role="user", content=[TextContent(text="Hello")]),
        ]

        with patch.object(
            adapter,
            "_count_tokens_api",
            new_callable=AsyncMock,
            return_value=42,
        ):
            count = await adapter.estimate_tokens(messages)
            assert count == 42


# ---------------------------------------------------------------------------
# max_context_tokens
# ---------------------------------------------------------------------------


class TestMaxContextTokens:
    def test_opus(self, adapter: ClaudeAdapter) -> None:
        assert adapter.max_context_tokens("claude-opus-4-20250514") == 1_000_000

    def test_sonnet_4_6(self, adapter: ClaudeAdapter) -> None:
        assert adapter.max_context_tokens("claude-sonnet-4-6-20250514") == 1_000_000

    def test_sonnet_4_5(self, adapter: ClaudeAdapter) -> None:
        assert adapter.max_context_tokens("claude-sonnet-4-5-20250514") == 200_000

    def test_haiku(self, adapter: ClaudeAdapter) -> None:
        assert adapter.max_context_tokens("claude-haiku-4-5-20250514") == 200_000

    def test_unknown_model(self, adapter: ClaudeAdapter) -> None:
        assert adapter.max_context_tokens("some-future-model") == 200_000


# ---------------------------------------------------------------------------
# cache_control_hints
# ---------------------------------------------------------------------------


class TestCacheControlHints:
    def test_system_prompt_cached(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="system", content=[TextContent(text="instructions")]),
            CanonicalMessage(role="user", content=[TextContent(text="hello")]),
        ]
        hints = adapter.cache_control_hints(messages)
        system_hints = [h for h in hints if h["message_index"] == 0]
        assert len(system_hints) == 1
        assert system_hints[0]["cache_control"] == {"type": "ephemeral"}

    def test_last_user_message_cached(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(role="user", content=[TextContent(text="first")], token_count=500),
            CanonicalMessage(
                role="assistant", content=[TextContent(text="reply")], token_count=500
            ),
            CanonicalMessage(role="user", content=[TextContent(text="second")], token_count=100),
        ]
        hints = adapter.cache_control_hints(messages)
        last_user_hints = [h for h in hints if h["message_index"] == 2]
        assert len(last_user_hints) >= 1

    def test_empty_messages(self, adapter: ClaudeAdapter) -> None:
        hints = adapter.cache_control_hints([])
        assert hints == []

    def test_tool_use_chain_not_broken(self, adapter: ClaudeAdapter) -> None:
        messages = [
            CanonicalMessage(
                role="assistant",
                content=[
                    ThinkingContent(thinking="...", signature="sig"),
                    ToolUseContent(tool_use_id="tu_1", name="fn", input={}),
                ],
                metadata={"stop_reason": "tool_use"},
                token_count=2000,
            ),
        ]
        hints = adapter.cache_control_hints(messages)
        # Tool-use chain messages should be skipped
        tool_use_hints = [h for h in hints if h["message_index"] == 0]
        assert len(tool_use_hints) == 0
