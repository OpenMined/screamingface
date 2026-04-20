"""Unit tests for the CoreMessage pydantic types.

Pure pydantic round-trips. No FastAPI, no httpx, no I/O.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ImagePart,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)


class TestTextPart:
    def test_roundtrip(self):
        p = TextPart(text="hello")
        assert p.type == "text"
        assert p.text == "hello"
        assert p.model_dump()["type"] == "text"

    def test_json_roundtrip(self):
        p = TextPart(text="hi")
        loaded = TextPart.model_validate_json(p.model_dump_json())
        assert loaded == p

    def test_provider_metadata_preserved(self):
        p = TextPart(text="hi", provider_metadata={"cache_control": {"type": "ephemeral"}})
        assert p.provider_metadata == {"cache_control": {"type": "ephemeral"}}

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            TextPart(text="hi", bogus="field")  # type: ignore[call-arg]


class TestImagePart:
    def test_url_source(self):
        p = ImagePart(image_url="https://example.com/img.png", media_type="image/png")
        assert p.image_url == "https://example.com/img.png"
        assert p.image_b64 is None
        assert p.media_type == "image/png"

    def test_base64_source(self):
        p = ImagePart(image_b64="iVBOR...", media_type="image/png")
        assert p.image_b64 == "iVBOR..."
        assert p.image_url is None


class TestToolCallPart:
    def test_basic(self):
        p = ToolCallPart(tool_call_id="call_1", tool_name="search", input={"q": "pandas"})
        assert p.type == "tool-call"
        assert p.tool_call_id == "call_1"
        assert p.tool_name == "search"
        assert p.input == {"q": "pandas"}

    def test_empty_input_default(self):
        p = ToolCallPart(tool_call_id="call_1", tool_name="search")
        assert p.input == {}


class TestToolResultPart:
    def test_success(self):
        p = ToolResultPart(tool_call_id="call_1", tool_name="search", output={"rows": 5})
        assert p.type == "tool-result"
        assert p.output == {"rows": 5}
        assert p.is_error is False

    def test_error(self):
        p = ToolResultPart(
            tool_call_id="call_1",
            tool_name="search",
            output="timeout",
            is_error=True,
        )
        assert p.is_error is True
        assert p.output == "timeout"


class TestReasoningPart:
    def test_with_signature(self):
        p = ReasoningPart(text="thinking...", signature="sig-abc")
        assert p.type == "reasoning"
        assert p.signature == "sig-abc"

    def test_without_signature(self):
        p = ReasoningPart(text="thinking...")
        assert p.signature is None


class TestCoreMessage:
    def test_string_content_shorthand(self):
        m = CoreMessage(role="user", content="hi")
        assert m.content == "hi"

    def test_list_content(self):
        m = CoreMessage(
            role="user",
            content=[TextPart(text="hi"), TextPart(text="there")],
        )
        assert isinstance(m.content, list)
        assert len(m.content) == 2

    def test_mixed_parts(self):
        m = CoreMessage(
            role="assistant",
            content=[
                TextPart(text="Let me search."),
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="search",
                    input={"q": "pandas"},
                ),
            ],
        )
        assert isinstance(m.content, list)
        assert len(m.content) == 2
        assert m.content[0].type == "text"
        assert m.content[1].type == "tool-call"

    def test_roles(self):
        for role in ("system", "user", "assistant", "tool"):
            CoreMessage(role=role, content="x")  # no validation error

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            CoreMessage(role="wizard", content="x")  # type: ignore[arg-type]

    def test_json_roundtrip_preserves_types(self):
        m = CoreMessage(
            role="user",
            content=[
                TextPart(text="look at this"),
                ImagePart(image_url="https://ex.com/a.png"),
                ToolResultPart(
                    tool_call_id="c1",
                    tool_name="web_fetch",
                    output={"html": "<p>hi</p>"},
                ),
            ],
        )
        as_json = m.model_dump_json()
        loaded = CoreMessage.model_validate_json(as_json)
        # pydantic discriminated union should reconstruct each part as its type
        assert isinstance(loaded.content, list)
        assert loaded.content[0].type == "text"
        assert loaded.content[1].type == "image"
        assert loaded.content[2].type == "tool-result"

    def test_provider_metadata_at_message_level(self):
        m = CoreMessage(
            role="user",
            content="hi",
            provider_metadata={"request_id": "req_abc"},
        )
        assert m.provider_metadata == {"request_id": "req_abc"}


class TestToolDefinition:
    def test_basic(self):
        t = ToolDefinition(
            name="get_weather",
            description="Get the current weather",
            input_schema={
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        )
        assert t.name == "get_weather"
        assert t.input_schema["type"] == "object"

    def test_default_input_schema(self):
        t = ToolDefinition(name="ping", description="Check liveness")
        assert t.input_schema == {"type": "object", "properties": {}}

    def test_json_serializable(self):
        t = ToolDefinition(
            name="get_weather",
            description="Get the current weather",
            input_schema={"type": "object", "properties": {}},
        )
        # Must round-trip through json.dumps cleanly (translators will do this)
        serialized = json.dumps(t.model_dump())
        assert "get_weather" in serialized
