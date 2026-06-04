"""Tests for claude_frontend terminal (ensemble-first) inference.

1. Unary and streaming inference synthesize in-memory (no api.anthropic.com).
2. Non-inference routes (catchall, count_tokens, /api/*) still forward upstream.
3. Error paths (static-None, resolution failure) return 200 with visible error text.
4. Streaming error paths terminate (message_stop frame).

Per the M2 adversarial-review corrections (#3): the success/terminal tests wire a
``_static_plugin()`` MagicMock whose ``get_active_expression()`` returns a STATIC
(no-``$prompt``) spec and ``resolve_context()`` returns the expected text — that is the
locus the success assertions exercise (NOT ``plugin=None``). The ``$prompt`` E2E path is
covered in ``test_e2e_claude_frontend.py``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def _static_plugin(resolved_text: str = "Ensemble result text") -> MagicMock:
    """A plugin with a STATIC (no-$prompt) active spec whose resolve_context returns text.

    This is the locus the success assertions exercise: resolve_static_context() reads
    ``plugin.resolve_context()`` directly (no blob store, no /ensemble).
    """
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "(https://example.com/robots.txt)"
    plugin.resolve_context.return_value = resolved_text
    return plugin


def parse_sse_frames(sse_text: str) -> list:
    frames = []
    current_event = None
    current_data = None
    for line in sse_text.split("\n"):
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:"):
            try:
                current_data = json.loads(line.replace("data:", "").strip())
            except json.JSONDecodeError:
                current_data = None
        elif line.strip() == "" and current_data is not None:
            frames.append((current_event, current_data))
            current_event = None
            current_data = None
    return frames


def test_unary_inference_synthesizes_response_no_upstream_call() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=_static_plugin("Ensemble result text")))
    client = TestClient(app)

    with patch("httpx.AsyncClient.post") as mock_httpx_post:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["content"][0]["text"] == "Ensemble result text"
    assert data["model"] == "claude-opus-4-1-20250805"
    assert data["stop_reason"] == "end_turn"
    assert "usage" in data
    assert not mock_httpx_post.called


def test_streaming_inference_synthesizes_sse_no_upstream_call() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=_static_plugin("Streamed result text")))
    client = TestClient(app)

    with patch("httpx.AsyncClient.stream") as mock_httpx_stream:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "Test"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    event_names = [n for n, _ in frames]
    assert event_names == [
        "message_start",
        "ping",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    delta_frame = next(d for n, d in frames if n == "content_block_delta")
    assert delta_frame["delta"]["text"] == "Streamed result text"
    assert not mock_httpx_stream.called


def test_static_spec_none_returns_error_envelope_fail_loud() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="broken-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = "some_expression"
    mock_plugin.resolve_context.return_value = None
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-opus-4-1-20250805",
            "messages": [{"role": "user", "content": "Test"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "message"
    assert "[url4 error]" in data["content"][0]["text"]
    assert "broken-spec" in data["content"][0]["text"]


def test_no_spec_synthesizes_empty_envelope_no_upstream_call() -> None:
    """No active spec → empty synthesized envelope, no upstream inference call (#3)."""
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="test-spec",
    )
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = None
    app = FastAPI()
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)

    with patch("httpx.AsyncClient.post") as mock_post:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "message"
    assert data["content"][0]["text"] == ""
    assert not mock_post.called


def test_count_tokens_forwards_upstream_not_terminated() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="test-spec"
    )
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"input_tokens": 50})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
        response = client.post(
            "/v1/messages/count_tokens",
            json={"messages": [{"role": "user", "content": "test"}]},
        )
    assert response.status_code == 200
    assert response.json()["input_tokens"] == 50


def test_v1_models_forwards_upstream() -> None:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"data": [{"id": "claude-3-5-sonnet"}]})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
        response = client.get("/v1/models")
    assert response.status_code == 200
    assert "data" in response.json()


def test_api_passthrough_forwards_upstream() -> None:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"users": []})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
        response = client.get("/api/users")
    assert response.status_code == 200
    assert "users" in response.json()


def test_streaming_error_terminates_with_message_stop_frame() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="broken-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = "bad_expression"
    mock_plugin.resolve_context.side_effect = RuntimeError("Spec eval failed")
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-opus-4-1-20250805",
            "messages": [{"role": "user", "content": "Test"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    event_names = [n for n, _ in frames]
    assert "message_stop" in event_names
    assert any(
        "[url4 error]" in d.get("delta", {}).get("text", "")
        for n, d in frames
        if n == "content_block_delta"
    )
