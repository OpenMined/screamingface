"""Tests for claude-frontend Anthropic API models and system prompt injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.models import (
    ContentBlockDelta,
    ContentBlockStart,
    Message,
    MessagesRequest,
    MessagesResponse,
    StreamMessageStart,
    TextBlock,
    ToolUseBlock,
    prepend_system_context,
)
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router

# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


class TestMessagesRequest:
    def test_minimal(self) -> None:
        req = MessagesRequest.model_validate(
            {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hi"}],
            }
        )
        assert req.model == "claude-sonnet-4-20250514"
        assert req.max_tokens == 1024
        assert len(req.messages) == 1
        assert req.messages[0].role == "user"
        assert req.messages[0].content == "Hi"
        assert req.system is None
        assert req.stream is None

    def test_full_request(self) -> None:
        req = MessagesRequest.model_validate(
            {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": "Hello"}],
                "system": "You are helpful",
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "stop_sequences": ["END"],
                "stream": True,
                "tools": [
                    {
                        "name": "get_weather",
                        "description": "Get weather",
                        "input_schema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    }
                ],
                "tool_choice": {"type": "auto"},
            }
        )
        assert req.system == "You are helpful"
        assert req.temperature == 0.7
        assert req.stream is True
        assert req.tools is not None
        assert len(req.tools) == 1
        assert req.tools[0].name == "get_weather"

    def test_system_as_list(self) -> None:
        req = MessagesRequest.model_validate(
            {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hi"}],
                "system": [{"type": "text", "text": "Be helpful"}],
            }
        )
        assert isinstance(req.system, list)
        assert len(req.system) == 1
        assert req.system[0].text == "Be helpful"

    def test_extra_fields_preserved(self) -> None:
        raw = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hi"}],
            "anthropic_beta": "some-beta-flag",
            "custom_field": 42,
        }
        req = MessagesRequest.model_validate(raw)
        dumped = req.model_dump(exclude_none=True)
        assert dumped["anthropic_beta"] == "some-beta-flag"
        assert dumped["custom_field"] == 42

    def test_without_max_tokens(self) -> None:
        req = MessagesRequest.model_validate(
            {
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            }
        )
        assert req.max_tokens is None

    def test_round_trip_fidelity(self) -> None:
        raw = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2048,
            "messages": [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi there!"}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Use this tool"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu_123",
                            "content": "result data",
                        },
                    ],
                },
            ],
            "system": "Be concise",
            "temperature": 0.5,
        }
        req = MessagesRequest.model_validate(raw)
        dumped = req.model_dump(exclude_none=True)
        assert dumped["model"] == raw["model"]
        assert dumped["max_tokens"] == raw["max_tokens"]
        assert dumped["system"] == raw["system"]
        assert dumped["temperature"] == raw["temperature"]
        assert len(dumped["messages"]) == 3


class TestContentBlocks:
    def test_text_block(self) -> None:
        msg = Message.model_validate(
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}
        )
        assert isinstance(msg.content, list)
        assert isinstance(msg.content[0], TextBlock)
        assert msg.content[0].text == "hello"

    def test_tool_use_block(self) -> None:
        msg = Message.model_validate(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "get_weather",
                        "input": {"city": "NYC"},
                    }
                ],
            }
        )
        assert isinstance(msg.content, list)
        block = msg.content[0]
        assert isinstance(block, ToolUseBlock)
        assert block.name == "get_weather"
        assert block.input == {"city": "NYC"}

    def test_string_content(self) -> None:
        msg = Message.model_validate({"role": "user", "content": "plain string"})
        assert msg.content == "plain string"

    def test_image_block(self) -> None:
        msg = Message.model_validate(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBOR...",
                        },
                    }
                ],
            }
        )
        assert isinstance(msg.content, list)
        assert msg.content[0].source.media_type == "image/png"  # type: ignore[union-attr]


class TestMessagesResponse:
    def test_parse(self) -> None:
        resp = MessagesResponse.model_validate(
            {
                "id": "msg_abc",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello!"}],
                "model": "claude-sonnet-4-20250514",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        assert resp.id == "msg_abc"
        assert resp.usage.input_tokens == 10
        assert isinstance(resp.content[0], TextBlock)


class TestStreamingEvents:
    def test_message_start(self) -> None:
        evt = StreamMessageStart.model_validate(
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 5, "output_tokens": 0},
                },
            }
        )
        assert evt.message.id == "msg_1"

    def test_content_block_start(self) -> None:
        evt = ContentBlockStart.model_validate(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }
        )
        assert evt.index == 0

    def test_content_block_delta(self) -> None:
        evt = ContentBlockDelta.model_validate(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hello"},
            }
        )
        assert evt.delta.text == "Hello"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# prepend_system_context tests
# ---------------------------------------------------------------------------


class TestPrependSystemContext:
    def test_prepend_to_none(self) -> None:
        req = MessagesRequest(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hi")],
        )
        prepend_system_context(req, "extra context")
        assert req.system == "extra context"

    def test_prepend_to_string(self) -> None:
        req = MessagesRequest(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hi")],
            system="original prompt",
        )
        prepend_system_context(req, "extra context")
        assert req.system == "extra context\n\noriginal prompt"

    def test_prepend_to_list(self) -> None:
        req = MessagesRequest(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hi")],
            system=[TextBlock(text="original")],
        )
        prepend_system_context(req, "extra context")
        assert isinstance(req.system, list)
        assert len(req.system) == 2
        assert req.system[0].text == "extra context\n\n"
        assert req.system[1].text == "original"

    def test_empty_context_noop(self) -> None:
        req = MessagesRequest(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hi")],
            system="original",
        )
        prepend_system_context(req, "")
        assert req.system == "original"


# ---------------------------------------------------------------------------
# Proxy integration tests (cached context injection)
# ---------------------------------------------------------------------------


class _FakePlugin:
    def __init__(self, context: str | None = None) -> None:
        self._context = context

    def resolve_context(self) -> str | None:
        return self._context


@pytest.fixture
def proxy_app_with_context() -> FastAPI:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    router = create_router(settings, plugin=_FakePlugin("cached url4 docs"))
    app.include_router(router)
    return app


@pytest.fixture
def proxy_app_no_context() -> FastAPI:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    router = create_router(settings)
    app.include_router(router)
    return app


_INJECT_PREFIX = (
    "Please be accurate and keep this information constantly in your context:\n\n"
)


class TestProxyContextInjection:
    prefix = _INJECT_PREFIX

    def test_injects_cached_context(self, proxy_app_with_context: FastAPI) -> None:
        client = TestClient(proxy_app_with_context)
        mock_response = httpx.Response(200, json={"id": "msg_1", "content": []})

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "system": "Be helpful",
                },
                headers={"x-api-key": "test-key"},
            )

        call_kwargs = mock_post.call_args
        sent_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json", {})
        assert sent_body["system"] == f"Be helpful\n\n{self.prefix}cached url4 docs"

    def test_no_context_passthrough(self, proxy_app_no_context: FastAPI) -> None:
        client = TestClient(proxy_app_no_context)
        mock_response = httpx.Response(200, json={"id": "msg_2", "content": []})

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "system": "Be helpful",
                },
                headers={"x-api-key": "test-key"},
            )

        call_kwargs = mock_post.call_args
        sent_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json", {})
        assert sent_body["system"] == "Be helpful"

    def test_extra_fields_survive_round_trip(self, proxy_app_with_context: FastAPI) -> None:
        client = TestClient(proxy_app_with_context)
        mock_response = httpx.Response(200, json={"id": "msg_3", "content": []})

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "unknown_field": "should survive",
                },
                headers={"x-api-key": "test-key"},
            )

        call_kwargs = mock_post.call_args
        sent_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json", {})
        assert sent_body["unknown_field"] == "should survive"

    def test_context_injected_into_none_system(self, proxy_app_with_context: FastAPI) -> None:
        client = TestClient(proxy_app_with_context)
        mock_response = httpx.Response(200, json={"id": "msg_4", "content": []})

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                    # No system prompt
                },
                headers={"x-api-key": "test-key"},
            )

        call_kwargs = mock_post.call_args
        sent_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json", {})
        assert isinstance(sent_body["system"], list)
        assert sent_body["system"][0]["text"] == f"{self.prefix}cached url4 docs"

    def test_context_injected_into_list_system(self, proxy_app_with_context: FastAPI) -> None:
        client = TestClient(proxy_app_with_context)
        mock_response = httpx.Response(200, json={"id": "msg_5", "content": []})

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "system": [{"type": "text", "text": "original"}],
                },
                headers={"x-api-key": "test-key"},
            )

        call_kwargs = mock_post.call_args
        sent_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json", {})
        assert isinstance(sent_body["system"], list)
        assert len(sent_body["system"]) == 2
        assert sent_body["system"][0]["text"] == "original"
        assert sent_body["system"][-1]["text"] == f"{self.prefix}cached url4 docs"
