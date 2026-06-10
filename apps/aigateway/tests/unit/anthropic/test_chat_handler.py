from __future__ import annotations

import httpx
import pytest

from aigateway.plugins.anthropic_provider.chat_handler import (
    _build_billing_header,
    chat_completion,
    prepare_claude_code_body,
)

pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'Logging.async_success_handler' was never awaited:RuntimeWarning"
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(
        self,
        url,
        *,
        headers=None,
        json=None,
        data=None,
        timeout=None,
        logging_obj=None,
        **_kwargs,
    ) -> httpx.Response:
        self.calls.append({"url": url, "headers": headers, "json": json, "data": data})
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "ready"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
        )


def test_prepare_claude_code_body_uses_top_level_system_escape_hatch() -> None:
    body = {
        "model": "anthropic/claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Reply exactly: ready"},
        ],
    }

    out = prepare_claude_code_body(body)

    assert out["system"][0] == {
        "type": "text",
        "text": _build_billing_header("Reply exactly: ready"),
    }
    assert out["system"][0]["text"].startswith("x-anthropic-billing-header: cc_version=2.1.142.")
    assert out["system"][0]["text"].endswith("; cc_entrypoint=cli; cch=00000;")
    assert out["system"][1] == {"type": "text", "text": "You are concise."}
    assert out["messages"] == [{"role": "user", "content": "Reply exactly: ready"}]


def test_prepare_claude_code_body_is_idempotent() -> None:
    body = {
        "model": "anthropic/claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Reply exactly: ready"},
        ],
    }

    once = prepare_claude_code_body(body)
    twice = prepare_claude_code_body(once)

    assert twice["system"] == once["system"]
    assert twice["messages"] == once["messages"]


@pytest.mark.asyncio
async def test_chat_completion_preserves_billing_header_through_litellm() -> None:
    client = FakeClient()

    response = await chat_completion(
        {
            "model": "anthropic/claude-sonnet-4-6",
            "api_key": "sk-ant-oat01-test",
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Reply exactly: ready"},
            ],
            "max_tokens": 20,
            "client": client,
            "no-log": True,
        }
    )

    sent = client.calls[-1]["json"]
    assert sent["system"][0]["text"].startswith("x-anthropic-billing-header:")
    assert sent["system"][1] == {"type": "text", "text": "You are concise."}
    assert sent["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Reply exactly: ready"}]}
    ]
    assert response.choices[0].message.content == "ready"


@pytest.mark.asyncio
async def test_api_key_request_carries_no_billing_header_and_uses_x_api_key() -> None:
    """Raw API keys are billed directly: no Claude-Code attribution block may
    be injected (audit F02), and LiteLLM must send the key as x-api-key, not
    Authorization (audit F18 — the plan's pinned litellm-upgrade risk)."""
    client = FakeClient()

    response = await chat_completion(
        {
            "model": "anthropic/claude-sonnet-4-6",
            "api_key": "sk-ant-api03-raw-key",
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Reply exactly: ready"},
            ],
            "max_tokens": 20,
            "client": client,
            "no-log": True,
        }
    )

    sent = client.calls[-1]
    headers = {str(k).lower(): v for k, v in (sent["headers"] or {}).items()}
    assert headers["x-api-key"] == "sk-ant-api03-raw-key"
    assert "authorization" not in headers
    assert "oauth" not in str(headers.get("anthropic-beta", ""))
    body_text = str(sent["json"])
    assert "x-anthropic-billing-header" not in body_text
    assert response.choices[0].message.content == "ready"


@pytest.mark.asyncio
async def test_oauth_request_uses_bearer_authorization_header() -> None:
    """The sk-ant-oat prefix is what selects the OAuth treatment in LiteLLM —
    pin it so an upgrade changing the routing fails loudly (audit F18)."""
    client = FakeClient()

    await chat_completion(
        {
            "model": "anthropic/claude-sonnet-4-6",
            "api_key": "sk-ant-oat01-test",
            "messages": [{"role": "user", "content": "Reply exactly: ready"}],
            "max_tokens": 20,
            "client": client,
            "no-log": True,
        }
    )

    headers = {str(k).lower(): v for k, v in (client.calls[-1]["headers"] or {}).items()}
    assert headers.get("authorization") == "Bearer sk-ant-oat01-test"
    assert "x-api-key" not in headers


@pytest.mark.asyncio
async def test_tools_remain_mapped_by_litellm() -> None:
    client = FakeClient()

    await chat_completion(
        {
            "model": "anthropic/claude-haiku-4-5",
            "api_key": "sk-ant-oat01-test",
            "messages": [{"role": "user", "content": "weather"}],
            "max_tokens": 20,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather.",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
            "client": client,
            "no-log": True,
        }
    )

    sent = client.calls[-1]["json"]
    assert sent["tools"] == [
        {
            "name": "get_weather",
            "description": "Get weather.",
            "type": "custom",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        }
    ]
    assert sent["tool_choice"] == {"type": "tool", "name": "get_weather"}
