"""Unit tests for codex-backend-api OpenAIResponsesAdapter.

Tests CoreMessage <-> OpenAI Responses API format conversions.
"""

from __future__ import annotations

import json

import pytest

from screamingface.plugins.codex_backend_api.adapter import OpenAIResponsesAdapter
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)

adapter = OpenAIResponsesAdapter()


# ----------------------------------------------------------------------------
# to_provider_format — basic
# ----------------------------------------------------------------------------


class TestToProviderFormatBasic:
    def test_single_user_text_uses_string_shorthand(self):
        msgs = [CoreMessage(role="user", content="Hello")]
        body = adapter.to_provider_format(msgs, model="o4-mini")
        assert body["model"] == "o4-mini"
        assert body["max_output_tokens"] == 16000
        # Single user text -> string shorthand
        assert body["input"] == "Hello"

    def test_system_becomes_instructions(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="o4-mini", system="Be concise")
        assert body["instructions"] == "Be concise"
        assert body["input"] == "Hi"

    def test_system_role_messages_merged_into_instructions(self):
        msgs = [
            CoreMessage(role="system", content="Rule 1"),
            CoreMessage(role="system", content="Rule 2"),
            CoreMessage(role="user", content="Hi"),
        ]
        body = adapter.to_provider_format(msgs, model="o4-mini", system="Base")
        assert "Base" in body["instructions"]
        assert "Rule 1" in body["instructions"]
        assert "Rule 2" in body["instructions"]

    def test_temperature_included_when_set(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="o4-mini", temperature=0.7)
        assert body["temperature"] == 0.7

    def test_temperature_omitted_when_none(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="o4-mini")
        assert "temperature" not in body

    def test_multi_message_uses_array(self):
        msgs = [
            CoreMessage(role="user", content="Hello"),
            CoreMessage(role="assistant", content="Hi there"),
            CoreMessage(role="user", content="How are you?"),
        ]
        body = adapter.to_provider_format(msgs, model="o4-mini")
        assert isinstance(body["input"], list)
        assert len(body["input"]) == 3


# ----------------------------------------------------------------------------
# to_provider_format — tool calls
# ----------------------------------------------------------------------------


class TestToProviderFormatToolCalls:
    def test_assistant_tool_call_becomes_function_call(self):
        msgs = [
            CoreMessage(
                role="assistant",
                content=[
                    TextPart(text="Let me search"),
                    ToolCallPart(
                        tool_call_id="call_123",
                        tool_name="search",
                        input={"query": "python"},
                    ),
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="o4-mini")
        items = body["input"]
        assert isinstance(items, list)
        # Should have text message + function_call
        text_item = next(i for i in items if i.get("role") == "assistant")
        assert text_item["content"] == "Let me search"
        fc_item = next(i for i in items if i.get("type") == "function_call")
        assert fc_item["call_id"] == "call_123"
        assert fc_item["name"] == "search"
        assert json.loads(fc_item["arguments"]) == {"query": "python"}

    def test_tool_result_becomes_function_call_output(self):
        msgs = [
            CoreMessage(
                role="tool",
                content=[
                    ToolResultPart(
                        tool_call_id="call_123",
                        tool_name="search",
                        output="results here",
                    ),
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="o4-mini")
        items = body["input"]
        assert isinstance(items, list)
        fco = items[0]
        assert fco["type"] == "function_call_output"
        assert fco["call_id"] == "call_123"
        assert fco["output"] == "results here"

    def test_tool_definitions(self):
        tools = [
            ToolDefinition(
                name="search",
                description="Search the web",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            )
        ]
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="o4-mini", tools=tools)
        assert len(body["tools"]) == 1
        t = body["tools"][0]
        assert t["type"] == "function"
        assert t["name"] == "search"
        assert t["description"] == "Search the web"
        assert t["parameters"]["type"] == "object"

    def test_reasoning_part_dropped(self):
        msgs = [
            CoreMessage(
                role="assistant",
                content=[
                    ReasoningPart(text="thinking..."),
                    TextPart(text="answer"),
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="o4-mini")
        items = body["input"]
        assert isinstance(items, list)
        text_item = next(i for i in items if i.get("role") == "assistant")
        assert text_item["content"] == "answer"


# ----------------------------------------------------------------------------
# from_provider_response
# ----------------------------------------------------------------------------


class TestFromProviderResponse:
    def test_text_response(self):
        data = {
            "id": "resp_test",
            "object": "response",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Hello!"}],
                }
            ],
            "model": "o4-mini",
            "status": "completed",
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        }
        msg = adapter.from_provider_response(data)
        assert msg.role == "assistant"
        assert isinstance(msg.content, list)
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextPart)
        assert msg.content[0].text == "Hello!"

    def test_function_call_response(self):
        data = {
            "id": "resp_test",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_abc",
                    "name": "get_weather",
                    "arguments": '{"city": "SF"}',
                }
            ],
        }
        msg = adapter.from_provider_response(data)
        assert len(msg.content) == 1
        part = msg.content[0]
        assert isinstance(part, ToolCallPart)
        assert part.tool_call_id == "call_abc"
        assert part.tool_name == "get_weather"
        assert part.input == {"city": "SF"}

    def test_provider_metadata(self):
        data = {
            "id": "resp_test",
            "model": "o4-mini",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "ok"}],
                }
            ],
            "status": "completed",
            "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
        }
        msg = adapter.from_provider_response(data)
        assert msg.provider_metadata is not None
        assert msg.provider_metadata["openai.id"] == "resp_test"
        assert msg.provider_metadata["openai.model"] == "o4-mini"
        assert msg.provider_metadata["openai.status"] == "completed"
        assert msg.provider_metadata["openai.usage"]["total_tokens"] == 7

    def test_non_dict_raises(self):
        with pytest.raises(AdapterError, match="not a dict"):
            adapter.from_provider_response("not a dict")  # type: ignore[arg-type]

    def test_empty_output_raises(self):
        with pytest.raises(AdapterError, match="empty 'output'"):
            adapter.from_provider_response({"output": []})

    def test_missing_output_raises(self):
        with pytest.raises(AdapterError, match="empty 'output'"):
            adapter.from_provider_response({"id": "test"})

    def test_text_and_function_call_together(self):
        data = {
            "id": "test",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "I'll search"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "search",
                    "arguments": "{}",
                },
            ],
        }
        msg = adapter.from_provider_response(data)
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextPart)
        assert isinstance(msg.content[1], ToolCallPart)
