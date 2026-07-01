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
from screamingface.plugins.backend_api_base.models import BackendProfile


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


def _fallback_factory(captured_models: list[str]):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode())
        captured_models.append(body["model"])
        if body["model"] == "anthropic/claude-sonnet-4-5":
            return httpx.Response(
                429,
                json={"detail": {"code": "rate_limited", "message": "limited"}},
            )
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "fallback pong"},
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
    gateway_provider = plugin.gateway_provider
    assert gateway_provider is not None

    # Inject the mocked HTTP factory by replacing _make_interpreter behavior:
    # easiest path is to swap the backend on the interpreter the plugin would build.
    backend = AigwBackend(
        gateway_url=plugin.settings.gateway_url,
        profile_name=plugin.settings.auth_profile,
        gateway_provider=gateway_provider,
        http_client_factory=factory,
    )
    interpreter = AigwInterpreter(
        app=None,
        settings=plugin.settings,
        backend=backend,
        gateway_provider=gateway_provider,
    )

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


@pytest.mark.anyio
async def test_interpreter_retries_fallback_model_on_429() -> None:
    captured_models: list[str] = []
    settings = AigwClaudeBackendSettings()
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider="anthropic",
        http_client_factory=_fallback_factory(captured_models),
    )
    interpreter = AigwInterpreter(
        app=None,
        settings=settings,
        backend=backend,
        gateway_provider="anthropic",
    )

    out = await interpreter.process(sources="cats", intent="describe")

    assert out == "fallback pong"
    assert captured_models == [
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-haiku-4-5",
    ]


@pytest.mark.anyio
async def test_bare_path_uses_default_model_not_default_profile() -> None:
    """SF-346 plan negative assertion: a bare exact /claude(...) URL4 call runs
    settings.default_model through the interpreter and must NOT switch to a
    configured profile's model just because a default_profile is set. Alias
    dispatch is the only path that reads profiles; the bare path is unchanged."""
    captured: dict = {}
    factory = _factory_returning("pong", captured)
    settings = AigwClaudeBackendSettings(
        default_model="anthropic/claude-haiku-4-5",
        profiles={"other": BackendProfile(model="anthropic/claude-opus-4-1")},
        default_profile="other",
    )
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider="anthropic",
        http_client_factory=factory,
    )
    interpreter = AigwInterpreter(
        app=None,
        settings=settings,
        backend=backend,
        gateway_provider="anthropic",
    )

    await interpreter.process(sources="", intent="hi")

    assert captured["body"]["model"] == "anthropic/claude-haiku-4-5"  # settings.default_model
    assert captured["body"]["model"] != "anthropic/claude-opus-4-1"  # NOT default_profile's model
