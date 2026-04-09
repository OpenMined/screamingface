"""Tests for gemini-backend-api GeminiAdapter."""

from __future__ import annotations

import pytest

from screamingface.plugins.gemini_backend_api.adapter import GeminiAdapter
from screamingface.plugins.llm_base.errors import AdapterError
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ToolCallPart,
    ToolDefinition,
)

adapter = GeminiAdapter()


class TestToProviderFormat:
    def test_single_user(self):
        msgs = [CoreMessage(role="user", content="Hello")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert body["_model"] == "gemini-2.5-flash"
        assert len(body["contents"]) == 1
        assert body["contents"][0]["role"] == "user"
        assert body["contents"][0]["parts"][0]["text"] == "Hello"

    def test_system_becomes_instruction(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", system="Be concise")
        assert "Be concise" in body["systemInstruction"]["parts"][0]["text"]

    def test_temperature(self):
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", temperature=0.7)
        assert body["generationConfig"]["temperature"] == 0.7

    def test_tools(self):
        tools = [
            ToolDefinition(
                name="search",
                description="Search",
                input_schema={"type": "object"},
            )
        ]
        msgs = [CoreMessage(role="user", content="Hi")]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash", tools=tools)
        fd = body["tools"][0]["functionDeclarations"][0]
        assert fd["name"] == "search"

    def test_assistant_becomes_model_role(self):
        msgs = [
            CoreMessage(role="user", content="Hi"),
            CoreMessage(role="assistant", content="Hello"),
        ]
        body = adapter.to_provider_format(msgs, model="gemini-2.5-flash")
        assert body["contents"][1]["role"] == "model"


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

    def test_non_dict_raises(self):
        with pytest.raises(AdapterError):
            adapter.from_provider_response("not dict")

    def test_empty_candidates_raises(self):
        with pytest.raises(AdapterError):
            adapter.from_provider_response({"candidates": []})
