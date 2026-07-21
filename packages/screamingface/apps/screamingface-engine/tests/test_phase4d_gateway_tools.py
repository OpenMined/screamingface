from __future__ import annotations

import json

import httpx
import pytest
from model_fixtures import MODEL_ROUTES
from url4 import ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.gateway import GatewayClient, ToolCall


@pytest.mark.asyncio
async def test_gateway_turn_preserves_standard_tool_calls_and_messages() -> None:
    requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": '{"query":"Jetson Orin"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    messages: list[dict[str, object]] = [{"role": "user", "content": "Research this"}]
    tools = (
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search",
                "parameters": {"type": "object"},
            },
        },
    )

    turn = await gateway.turn(
        MODEL_ROUTES[2],
        messages=messages,
        params={"temperature": "0", "max_tokens": "8192"},
        tools=tools,
    )
    await gateway.aclose()

    assert turn.content is None
    assert turn.tool_calls == (ToolCall("call_1", "web_search", '{"query":"Jetson Orin"}'),)
    assert requests == [
        {
            "model": "anthropic/claude-sonnet-4-6",
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 8192,
            "tools": list(tools),
        }
    ]


@pytest.mark.asyncio
async def test_gateway_accepts_completed_openrouter_managed_tool_records() -> None:
    model = ModelRoute(
        "openrouter/google/gemini-3.1-pro-preview",
        "openrouter/google/gemini-3.1-pro-preview",
        "openrouter",
        ("web_search", "web_fetch"),
        "openrouter",
    )
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "Final answer with sources.",
                                "tool_calls": [
                                    {
                                        "id": "search-1",
                                        "type": "openrouter:web_search",
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        ),
    )
    turn = await gateway.turn(model, messages=[], params={}, tools=())
    await gateway.aclose()
    assert turn.content == "Final answer with sources."
    assert turn.tool_calls == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "error"),
    [
        ({"content": None}, "neither text nor tool calls"),
        ({"content": 7}, "invalid text content"),
        ({"content": None, "tool_calls": [{}]}, "invalid tool call"),
        (
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "x",
                        "type": "other",
                        "function": {"name": "web_search", "arguments": "{}"},
                    }
                ],
            },
            "invalid tool call",
        ),
    ],
)
async def test_gateway_turn_rejects_invalid_assistant_messages(
    message: dict[str, object], error: str
) -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"choices": [{"message": message}]})
        ),
    )

    with pytest.raises(ResolutionError, match=error):
        await gateway.turn(MODEL_ROUTES[2], messages=[], params={}, tools=())
    await gateway.aclose()
