"""AigwCodexBackend url4 dispatch routes through the Codex gateway provider."""

from __future__ import annotations

import json

import httpx
import pytest

from screamingface.plugins.aigw_base import AigwBackend, AigwInterpreter
from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendSettings,
)


def _factory_returning(text: str, captured: dict | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["url"] = str(req.url)
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "model": "codex/gpt-5.4-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    def factory(timeout: float):
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout))

    return factory


@pytest.mark.anyio
async def test_handle_backend_call_returns_assistant_text() -> None:
    captured: dict = {}
    settings = AigwCodexBackendSettings()
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider="codex",
        http_client_factory=_factory_returning("pong", captured),
    )
    interpreter = AigwInterpreter(app=None, settings=settings, backend=backend)

    out = await interpreter.process(sources="cats", intent="describe")

    assert out == "pong"
    assert captured["body"]["model"] == "codex/gpt-5.4-mini"
    assert captured["headers"]["x-profile"] == "default"
    assert captured["url"].endswith("/v1/chat/completions")
    user_msg = captured["body"]["messages"][-1]
    assert user_msg["role"] == "user"
    assert "describe" in user_msg["content"]
    assert "cats" in user_msg["content"]
