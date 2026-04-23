# pyright: reportOptionalSubscript=false, reportArgumentType=false
"""Unit tests for OllamaAdapter — CoreMessage <-> Ollama /api/chat shape."""

from __future__ import annotations

import pytest

from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ImagePart,
    TextPart,
    ToolDefinition,
)
from screamingface.plugins.ollama_backend_api.adapter import OllamaAdapter

adapter = OllamaAdapter()


# ----------------------------------------------------------------------------
# to_provider_format
# ----------------------------------------------------------------------------


class TestToProviderFormat:
    def test_stream_is_always_false(self):
        msgs = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(msgs, model="llama3")
        assert body["stream"] is False
        assert body["model"] == "llama3"
        assert body["messages"] == [{"role": "user", "content": "hi"}]

    def test_max_tokens_mapped_to_options_num_predict(self):
        msgs = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(msgs, model="llama3", max_tokens=500)
        assert body["options"] == {"num_predict": 500}

    def test_temperature_included_in_options(self):
        msgs = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(msgs, model="llama3", max_tokens=100, temperature=0.3)
        assert body["options"] == {"num_predict": 100, "temperature": 0.3}

    def test_system_prompt_prepended_as_first_message(self):
        msgs = [CoreMessage(role="user", content="Q")]
        body = adapter.to_provider_format(msgs, model="llama3", system="Be concise")
        assert body["messages"][0] == {"role": "system", "content": "Be concise"}
        assert body["messages"][1] == {"role": "user", "content": "Q"}

    def test_system_role_messages_merged_with_explicit_system(self):
        msgs = [
            CoreMessage(role="system", content="Rule 1"),
            CoreMessage(role="system", content="Rule 2"),
            CoreMessage(role="user", content="Hi"),
        ]
        body = adapter.to_provider_format(msgs, model="llama3", system="Base")
        assert body["messages"][0]["role"] == "system"
        content = body["messages"][0]["content"]
        assert "Base" in content and "Rule 1" in content and "Rule 2" in content
        assert body["messages"][1] == {"role": "user", "content": "Hi"}

    def test_list_of_text_parts_flattened_to_string(self):
        msgs = [
            CoreMessage(
                role="user",
                content=[TextPart(text="Hello "), TextPart(text="world")],
            )
        ]
        body = adapter.to_provider_format(msgs, model="llama3")
        assert body["messages"] == [{"role": "user", "content": "Hello world"}]

    def test_non_text_parts_dropped(self):
        msgs = [
            CoreMessage(
                role="user",
                content=[
                    TextPart(text="keep me"),
                    ImagePart(image_url="https://example.com/x.png"),
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="llama3")
        assert body["messages"][0]["content"] == "keep me"

    def test_tools_translated_to_function_schema(self):
        tools = [
            ToolDefinition(
                name="weather",
                description="Get weather",
                input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
            )
        ]
        msgs = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(msgs, model="llama3", tools=tools)
        assert body["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ]

    def test_no_options_key_when_defaults_would_be_empty(self):
        msgs = [CoreMessage(role="user", content="hi")]
        body = adapter.to_provider_format(msgs, model="llama3", max_tokens=0)
        assert "options" not in body


# ----------------------------------------------------------------------------
# from_provider_response
# ----------------------------------------------------------------------------


class TestFromProviderResponse:
    def test_basic_response_parsed(self):
        data = {
            "model": "llama3.2",
            "created_at": "2026-04-23T00:00:00Z",
            "message": {"role": "assistant", "content": "Hello!"},
            "done": True,
            "done_reason": "stop",
            "total_duration": 123456,
        }
        msg = adapter.from_provider_response(data)
        assert msg.role == "assistant"
        assert isinstance(msg.content, list)
        assert isinstance(msg.content[0], TextPart)
        assert msg.content[0].text == "Hello!"
        assert msg.provider_metadata is not None
        assert msg.provider_metadata["ollama.model"] == "llama3.2"
        assert msg.provider_metadata["ollama.done"] is True
        assert msg.provider_metadata["ollama.total_duration"] == 123456

    def test_empty_content_string(self):
        data = {"message": {"role": "assistant", "content": ""}, "done": True}
        msg = adapter.from_provider_response(data)
        assert isinstance(msg.content, list)
        assert isinstance(msg.content[0], TextPart)
        assert msg.content[0].text == ""

    def test_null_content_coerces_to_empty_string(self):
        data = {"message": {"role": "assistant", "content": None}, "done": True}
        msg = adapter.from_provider_response(data)
        assert isinstance(msg.content, list)
        assert isinstance(msg.content[0], TextPart)
        assert msg.content[0].text == ""

    def test_missing_message_raises(self):
        with pytest.raises(AdapterError, match="missing 'message'"):
            adapter.from_provider_response({"done": True})

    def test_non_dict_raises(self):
        with pytest.raises(AdapterError, match="not a dict"):
            adapter.from_provider_response("oops")  # type: ignore[arg-type]

    def test_non_string_content_raises(self):
        data = {"message": {"role": "assistant", "content": ["list", "instead"]}, "done": True}
        with pytest.raises(AdapterError, match="not a string"):
            adapter.from_provider_response(data)
