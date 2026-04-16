"""Unit tests for claude-backend-api AnthropicAdapter.

Covers CoreMessage ↔ Anthropic Messages round-trips, the orphan
tool_use/tool_result repair pass, and the system-prompt merging
behavior.
"""

from __future__ import annotations

import pytest

from screamingface.plugins.claude_backend_api.adapter import AnthropicAdapter
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)


@pytest.fixture
def adapter() -> AnthropicAdapter:
    return AnthropicAdapter()


# ----------------------------------------------------------------------------
# to_provider_format: basic message shapes
# ----------------------------------------------------------------------------


class TestToProviderFormatBasic:
    def test_single_user_text_message(self, adapter: AnthropicAdapter):
        messages = [CoreMessage(role="user", content=[TextPart(text="hi")])]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        assert body["model"] == "claude-sonnet-4-5"
        assert body["max_tokens"] == 16000
        assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    def test_string_content_shorthand_expanded(self, adapter: AnthropicAdapter):
        """CoreMessage with a bare string content gets wrapped in a text block."""
        messages = [CoreMessage(role="user", content="hello")]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")
        assert body["messages"][0]["content"] == [{"type": "text", "text": "hello"}]

    def test_system_arg_becomes_top_level_system(self, adapter: AnthropicAdapter):
        messages = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(
            messages, model="claude-sonnet-4-5", system="You are helpful."
        )
        # System is now an array with billing header + user system text
        assert isinstance(body["system"], list)
        assert body["system"][0]["type"] == "text"
        assert "x-anthropic-billing-header" in body["system"][0]["text"]
        assert body["system"][1] == {"type": "text", "text": "You are helpful."}

    def test_system_role_messages_merged_into_top_level(self, adapter: AnthropicAdapter):
        """CoreMessage(role="system", …) entries get hoisted into the
        top-level system field, not the messages array."""
        messages = [
            CoreMessage(role="system", content="rule 1"),
            CoreMessage(role="system", content="rule 2"),
            CoreMessage(role="user", content="hi"),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        # Billing header + two system chunks
        assert isinstance(body["system"], list)
        assert len(body["system"]) == 3
        assert "x-anthropic-billing-header" in body["system"][0]["text"]
        assert body["system"][1]["text"] == "rule 1"
        assert body["system"][2]["text"] == "rule 2"
        # Only the user message remains in messages array
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"

    def test_explicit_system_and_system_role_both_merge(self, adapter: AnthropicAdapter):
        """system arg comes first, then any system-role message contents."""
        messages = [
            CoreMessage(role="system", content="from message"),
            CoreMessage(role="user", content="hi"),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5", system="from arg")
        assert isinstance(body["system"], list)
        assert body["system"][1]["text"] == "from arg"
        assert body["system"][2]["text"] == "from message"

    def test_max_tokens_passed_through(self, adapter: AnthropicAdapter):
        messages = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5", max_tokens=500)
        assert body["max_tokens"] == 500

    def test_temperature_only_included_when_set(self, adapter: AnthropicAdapter):
        messages = [CoreMessage(role="user", content="hi")]
        body_default = adapter.to_provider_format(messages, model="claude-sonnet-4-5")
        body_explicit = adapter.to_provider_format(
            messages, model="claude-sonnet-4-5", temperature=0.7
        )
        assert "temperature" not in body_default
        assert body_explicit["temperature"] == 0.7


# ----------------------------------------------------------------------------
# to_provider_format: content block translation
# ----------------------------------------------------------------------------


class TestContentBlockTranslation:
    def test_tool_call_part_becomes_tool_use(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(
                role="user",
                content=[TextPart(text="call bash")],
            ),
            CoreMessage(
                role="assistant",
                content=[
                    ToolCallPart(
                        tool_call_id="toolu_01",
                        tool_name="Bash",
                        input={"command": "ls"},
                    )
                ],
            ),
            CoreMessage(
                role="user",
                content=[
                    ToolResultPart(
                        tool_call_id="toolu_01",
                        tool_name="Bash",
                        output="a.txt\nb.txt",
                    )
                ],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        assistant_msg = body["messages"][1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"][0] == {
            "type": "tool_use",
            "id": "toolu_01",
            "name": "Bash",
            "input": {"command": "ls"},
        }

        user_result_msg = body["messages"][2]
        assert user_result_msg["role"] == "user"
        assert user_result_msg["content"][0] == {
            "type": "tool_result",
            "tool_use_id": "toolu_01",
            "content": "a.txt\nb.txt",
        }

    def test_tool_result_with_dict_output_json_encoded(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(
                role="assistant",
                content=[
                    ToolCallPart(tool_call_id="t1", tool_name="search", input={"q": "pandas"})
                ],
            ),
            CoreMessage(
                role="user",
                content=[
                    ToolResultPart(
                        tool_call_id="t1",
                        tool_name="search",
                        output={"rows": 5, "top": "panda"},
                    )
                ],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        result_block = body["messages"][1]["content"][0]
        # dict output gets JSON-encoded as a string
        import json as _json

        assert _json.loads(result_block["content"]) == {"rows": 5, "top": "panda"}

    def test_tool_result_is_error_propagated(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(
                role="assistant",
                content=[ToolCallPart(tool_call_id="t1", tool_name="bash", input={"cmd": "x"})],
            ),
            CoreMessage(
                role="user",
                content=[
                    ToolResultPart(
                        tool_call_id="t1",
                        tool_name="bash",
                        output="cmd not found",
                        is_error=True,
                    )
                ],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")
        assert body["messages"][1]["content"][0]["is_error"] is True

    def test_reasoning_part_becomes_thinking_block(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(role="user", content="solve"),
            CoreMessage(
                role="assistant",
                content=[
                    ReasoningPart(text="Let me think...", signature="sig-1"),
                    TextPart(text="The answer is 42."),
                ],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")
        assistant = body["messages"][1]
        assert assistant["content"][0] == {
            "type": "thinking",
            "thinking": "Let me think...",
            "signature": "sig-1",
        }
        assert assistant["content"][1] == {"type": "text", "text": "The answer is 42."}


# ----------------------------------------------------------------------------
# to_provider_format: tool definitions
# ----------------------------------------------------------------------------


class TestToolDefinitions:
    def test_tools_list_serialized(self, adapter: AnthropicAdapter):
        tools = [
            ToolDefinition(
                name="get_weather",
                description="Get current weather",
                input_schema={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ]
        body = adapter.to_provider_format(
            [CoreMessage(role="user", content="hi")],
            model="claude-sonnet-4-5",
            tools=tools,
        )
        assert body["tools"] == [
            {
                "name": "get_weather",
                "description": "Get current weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            }
        ]

    def test_no_tools_no_tools_field(self, adapter: AnthropicAdapter):
        body = adapter.to_provider_format(
            [CoreMessage(role="user", content="hi")], model="claude-sonnet-4-5"
        )
        assert "tools" not in body


# ----------------------------------------------------------------------------
# Orphan repair pass
# ----------------------------------------------------------------------------


class TestOrphanRepair:
    def test_valid_pair_kept(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(role="user", content="call tool"),
            CoreMessage(
                role="assistant",
                content=[ToolCallPart(tool_call_id="t1", tool_name="bash", input={"cmd": "ls"})],
            ),
            CoreMessage(
                role="user",
                content=[ToolResultPart(tool_call_id="t1", tool_name="bash", output="a.txt")],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")
        # All three messages survived
        assert len(body["messages"]) == 3
        # The tool_use and tool_result are both present
        types = [block.get("type") for msg in body["messages"] for block in msg["content"]]
        assert "tool_use" in types
        assert "tool_result" in types

    def test_orphan_tool_use_dropped(self, adapter: AnthropicAdapter):
        """Assistant tool_use with no matching user tool_result is dropped."""
        messages = [
            CoreMessage(role="user", content="call tool"),
            CoreMessage(
                role="assistant",
                content=[
                    TextPart(text="Let me try..."),
                    ToolCallPart(
                        tool_call_id="orphan_1",
                        tool_name="bash",
                        input={"cmd": "ls"},
                    ),
                ],
            ),
            # No user tool_result follows
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        # Assistant message survives but only the text block
        assistant = body["messages"][1]
        assert len(assistant["content"]) == 1
        assert assistant["content"][0]["type"] == "text"

    def test_orphan_tool_result_dropped(self, adapter: AnthropicAdapter):
        """User tool_result with no matching assistant tool_use is dropped."""
        messages = [
            CoreMessage(role="user", content="query"),
            CoreMessage(
                role="user",
                content=[
                    ToolResultPart(
                        tool_call_id="orphan_result",
                        tool_name="bash",
                        output="data",
                    )
                ],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        # The orphan-only user message should be dropped entirely
        # (it had no non-tool-result content)
        roles = [m["role"] for m in body["messages"]]
        # Only the first user message ("query") survives
        assert len(body["messages"]) == 1
        assert roles == ["user"]

    def test_mixed_orphan_and_valid_pair(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(
                role="assistant",
                content=[
                    ToolCallPart(tool_call_id="valid", tool_name="bash", input={"cmd": "ls"}),
                    ToolCallPart(tool_call_id="orphan", tool_name="bash", input={"cmd": "cat"}),
                ],
            ),
            CoreMessage(
                role="user",
                content=[ToolResultPart(tool_call_id="valid", tool_name="bash", output="a.txt")],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        assistant = body["messages"][0]
        # Only the valid tool_use survived
        tool_uses = [b for b in assistant["content"] if b["type"] == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["id"] == "valid"

    def test_message_with_only_orphan_blocks_dropped_entirely(self, adapter: AnthropicAdapter):
        messages = [
            CoreMessage(role="user", content="hi"),
            CoreMessage(
                role="assistant",
                content=[ToolCallPart(tool_call_id="orphan", tool_name="x", input={})],
            ),
        ]
        body = adapter.to_provider_format(messages, model="claude-sonnet-4-5")

        # Assistant message had ONLY the orphan → dropped entirely
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["user"]


# ----------------------------------------------------------------------------
# from_provider_response: parsing
# ----------------------------------------------------------------------------


class TestFromProviderResponse:
    def test_text_only_response(self, adapter: AnthropicAdapter):
        data = {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello!"}],
            "model": "claude-sonnet-4-5",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = adapter.from_provider_response(data)

        assert result.role == "assistant"
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "Hello!"

    def test_response_preserves_metadata_in_provider_metadata(self, adapter: AnthropicAdapter):
        data = {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi"}],
            "model": "claude-sonnet-4-5",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        result = adapter.from_provider_response(data)
        assert result.provider_metadata is not None
        assert result.provider_metadata["anthropic.id"] == "msg_01"
        assert result.provider_metadata["anthropic.model"] == "claude-sonnet-4-5"
        assert result.provider_metadata["anthropic.stop_reason"] == "end_turn"
        assert result.provider_metadata["anthropic.usage"] == {
            "input_tokens": 10,
            "output_tokens": 2,
        }

    def test_tool_use_in_response(self, adapter: AnthropicAdapter):
        data = {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Running command"},
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "Bash",
                    "input": {"command": "ls"},
                },
            ],
        }
        result = adapter.from_provider_response(data)

        assert len(result.content) == 2
        assert isinstance(result.content[0], TextPart)
        assert isinstance(result.content[1], ToolCallPart)
        assert result.content[1].tool_call_id == "toolu_01"
        assert result.content[1].tool_name == "Bash"
        assert result.content[1].input == {"command": "ls"}

    def test_thinking_block_in_response(self, adapter: AnthropicAdapter):
        data = {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Let me analyze...",
                    "signature": "sig-abc",
                },
                {"type": "text", "text": "Answer"},
            ],
        }
        result = adapter.from_provider_response(data)
        assert isinstance(result.content[0], ReasoningPart)
        assert result.content[0].text == "Let me analyze..."
        assert result.content[0].signature == "sig-abc"

    def test_unknown_block_type_dropped_silently(self, adapter: AnthropicAdapter):
        data = {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "future_block", "data": "?"},
            ],
        }
        result = adapter.from_provider_response(data)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextPart)


class TestFromProviderResponseErrors:
    def test_non_dict_raises(self, adapter: AnthropicAdapter):
        with pytest.raises(AdapterError, match="not a dict"):
            adapter.from_provider_response("not a dict")  # type: ignore[arg-type]

    def test_wrong_type_field_raises(self, adapter: AnthropicAdapter):
        with pytest.raises(AdapterError, match="expected 'message'"):
            adapter.from_provider_response({"type": "error", "role": "assistant"})

    def test_wrong_role_raises(self, adapter: AnthropicAdapter):
        with pytest.raises(AdapterError, match="expected 'assistant'"):
            adapter.from_provider_response({"type": "message", "role": "user", "content": []})

    def test_non_list_content_raises(self, adapter: AnthropicAdapter):
        with pytest.raises(AdapterError, match="not a list"):
            adapter.from_provider_response(
                {"type": "message", "role": "assistant", "content": "hi"}
            )
