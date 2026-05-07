"""End-to-end test: AigwClaudeBackendPlugin.handle_backend_call routes
through AigwInterpreter → AigwBackend (mocked transport) and returns
the assistant text."""

from __future__ import annotations

import json

import httpx
import pytest

from screamingface.plugins.aigw_base import AigwBackend, AigwInterpreter
from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
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
                "model": "anthropic/claude-sonnet-4-5",
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
    """The plugin's handle_backend_call uses the inherited _make_interpreter
    which constructs an AigwInterpreter that sends to the gateway."""
    captured: dict = {}
    factory = _factory_returning("pong", captured)

    plugin = AigwClaudeBackendPlugin()
    plugin.settings = AigwClaudeBackendSettings()  # type: ignore[assignment]

    # Inject the mocked HTTP factory by replacing _make_interpreter behavior:
    # easiest path is to swap the backend on the interpreter the plugin would build.
    backend = AigwBackend(
        gateway_url=plugin.settings.gateway_url,
        profile_name=plugin.settings.auth_profile,
        http_client_factory=factory,
    )
    interpreter = AigwInterpreter(app=None, settings=plugin.settings, backend=backend)

    out = await interpreter.process(sources="cats", intent="describe")
    assert out == "pong"

    # Body shape sanity
    assert captured["body"]["model"] == "anthropic/claude-sonnet-4-5"
    assert captured["headers"]["x-profile"] == "default"
    assert captured["url"].endswith("/v1/chat/completions")
    user_msg = captured["body"]["messages"][-1]
    assert user_msg["role"] == "user"
    assert "describe" in user_msg["content"]
    assert "cats" in user_msg["content"]
