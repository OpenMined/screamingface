"""Tests for gemini-backend-api GeminiAdapter."""

from __future__ import annotations

import pytest

from screamingface.plugins.gemini_backend_api.adapter import GeminiAdapter
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)

adapter = GeminiAdapter()


# ============================================================================
# to_provider_format tests
# ============================================================================


class TestToProviderFormat:
    def test_single_user(self):
        msgs = [CoreMessage(role="user", content="Hello")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert body["_model"] == "gemini-2.5-flash"
        assert len(body["contents"]) == 1
        assert body["contents"][0]["role"] == "user"
        assert body["contents"][0]["parts"][0]["text"] == "Hello"

    def test_string_content_expanded(self):
        """Bare string content gets wrapped in a parts list."""
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert body["contents"][0]["parts"] == [{"text": "Hi"}]

    def test_system_becomes_instruction(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", system="Be concise")
        assert "Be concise" in body["systemInstruction"]["parts"][0]["text"]

    def test_system_role_messages_merged(self):
        """System-role messages from the list are hoisted to systemInstruction."""
        msgs = [
            CoreMessage(role="system", content="Rule 1"),
            CoreMessage(role="user", content="Hi"),
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert "Rule 1" in body["systemInstruction"]["parts"][0]["text"]
        # System message should NOT appear in contents
        assert all(c["role"] != "system" for c in body["contents"])

    def test_explicit_system_and_system_role_both_merge(self):
        """Both the system= arg and system-role messages combine."""
        msgs = [
            CoreMessage(role="system", content="From list"),
            CoreMessage(role="user", content="Hi"),
        ]
        body = adapter.to_provider_format(
            msgs, model="gemini-2.5-flash", system="From arg"
        )
        combined = body["systemInstruction"]["parts"][0]["text"]
        assert "From arg" in combined
        assert "From list" in combined

    def test_max_tokens_passed_through(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", max_tokens=4096)
        assert body["generationConfig"]["maxOutputTokens"] == 4096

    def test_temperature(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", temperature=0.7)
        assert body["generationConfig"]["temperature"] == 0.7

    def test_temperature_omitted_when_none(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert "temperature" not in body["generationConfig"]

    def test_tools(self):
        tools = [
            ToolDefinition(
                name="search",
                description="Search the web",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            )
        ]
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", tools=tools)
        fd = body["tools"][0]["functionDeclarations"][0]
        assert fd["name"] == "search"
        assert fd["description"] == "Search the web"
        assert fd["parameters"]["type"] == "object"

    def test_no_tools_no_tools_field(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert "tools" not in body

    def test_assistant_becomes_model_role(self):
        msgs = [
            CoreMessage(role="user", content="Hi"),
            CoreMessage(role="assistant", content="Hello"),
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert body["contents"][1]["role"] == "model"


class TestContentBlockTranslation:
    def test_tool_call_part_becomes_function_call(self):
        msgs = [
            CoreMessage(
                role="assistant",
                content=[
                    ToolCallPart(
                        tool_call_id="call_1",
                        tool_name="get_weather",
                        input={"city": "SF"},
                    )
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        part = body["contents"][0]["parts"][0]
        assert part["functionCall"]["name"] == "get_weather"
        assert part["functionCall"]["args"] == {"city": "SF"}

    def test_tool_result_becomes_function_response(self):
        msgs = [
            CoreMessage(
                role="user",
                content=[
                    ToolResultPart(
                        tool_call_id="call_1",
                        tool_name="get_weather",
                        output={"temp": 72},
                    )
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        part = body["contents"][0]["parts"][0]
        assert part["functionResponse"]["name"] == "get_weather"
        assert part["functionResponse"]["response"] == {"temp": 72}

    def test_tool_result_string_output_wrapped(self):
        """String tool output gets wrapped in {"result": ...}."""
        msgs = [
            CoreMessage(
                role="user",
                content=[
                    ToolResultPart(
                        tool_call_id="call_1",
                        tool_name="search",
                        output="42",
                    )
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        part = body["contents"][0]["parts"][0]
        assert part["functionResponse"]["response"] == {"result": "42"}

    def test_multi_part_message(self):
        """Multiple parts in one message are serialized correctly."""
        msgs = [
            CoreMessage(
                role="assistant",
                content=[
                    TextPart(text="Let me check."),
                    ToolCallPart(tool_call_id="c1", tool_name="search", input={"q": "test"}),
                ],
            )
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        parts = body["contents"][0]["parts"]
        assert len(parts) == 2
        assert "text" in parts[0]
        assert "functionCall" in parts[1]


# ============================================================================
# from_provider_response tests
# ============================================================================


class TestFromProviderResponse:
    def test_text_response(self):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Hello!"}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 5,
                "candidatesTokenCount": 3,
            },
        }
        msg = adapter.from_provider_response(data)
        assert msg.role == "assistant"
        assert msg.content[0].text == "Hello!"

    def test_response_preserves_usage_metadata(self):
        data = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "Hi"}], "role": "model"},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
        }
        msg = adapter.from_provider_response(data)
        assert msg.provider_metadata["gemini.usage"]["promptTokenCount"] == 10
        assert msg.provider_metadata["gemini.usage"]["totalTokenCount"] == 15

    def test_response_preserves_finish_reason(self):
        data = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "done"}], "role": "model"},
                    "finishReason": "MAX_TOKENS",
                }
            ],
        }
        msg = adapter.from_provider_response(data)
        assert msg.provider_metadata["gemini.finish_reason"] == "MAX_TOKENS"

    def test_function_call_response(self):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"city": "SF"},
                                }
                            }
                        ],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
        }
        msg = adapter.from_provider_response(data)
        part = msg.content[0]
        assert isinstance(part, ToolCallPart)
        assert part.tool_name == "get_weather"
        assert part.input == {"city": "SF"}

    def test_mixed_text_and_function_call(self):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Let me check the weather."},
                            {"functionCall": {"name": "weather", "args": {}}},
                        ],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
        }
        msg = adapter.from_provider_response(data)
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextPart)
        assert isinstance(msg.content[1], ToolCallPart)

    def test_unknown_part_type_dropped(self):
        """Unknown part types (e.g. executableCode) are silently dropped."""
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "hi"},
                            {"executableCode": {"code": "print(1)"}},
                        ],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
        }
        msg = adapter.from_provider_response(data)
        assert len(msg.content) == 1
        assert msg.content[0].text == "hi"

    def test_empty_content_returns_empty_string(self):
        """Candidate with no usable parts returns empty string content."""
        data = {
            "candidates": [
                {
                    "content": {"parts": [], "role": "model"},
                    "finishReason": "STOP",
                }
            ],
        }
        msg = adapter.from_provider_response(data)
        assert msg.content == ""


class TestFromProviderResponseErrors:
    def test_non_dict_raises(self):
        with pytest.raises(AdapterError):
            adapter.from_provider_response("not dict")

    def test_empty_candidates_raises(self):
        with pytest.raises(AdapterError):
            adapter.from_provider_response({"candidates": []})

    def test_missing_candidates_raises(self):
        with pytest.raises(AdapterError):
            adapter.from_provider_response({"usageMetadata": {}})
