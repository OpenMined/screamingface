"""Tests for session integration in the claude_frontend proxy."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.hooks import HookRegistry
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import _parse_sse_response, create_router


class _FakePlugin:
    def __init__(self, context: str | None = None) -> None:
        self._context = context

    def resolve_context(self) -> str | None:
        return self._context


def _make_app(
    hooks: HookRegistry | None = None,
    session_service_url: str | None = None,
    plugin: _FakePlugin | None = None,
) -> FastAPI:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        session_service_url=session_service_url,
    )
    app = FastAPI()
    router = create_router(settings, plugin=plugin or _FakePlugin(), hooks=hooks)
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# _parse_sse_response tests
# ---------------------------------------------------------------------------


def _sse(*events: str) -> str:
    """Build SSE stream from individual event lines."""
    return "\n\n".join(f"data: {e}" for e in events) + "\n\n"


class TestParseSSEResponse:
    def test_simple_text(self) -> None:
        import json

        msg_start = json.dumps(
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 10, "output_tokens": 0},
                },
            }
        )
        raw = _sse(
            msg_start,
            '{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
            '{"type":"content_block_delta","index":0,'
            '"delta":{"type":"text_delta","text":" world"}}',
            '{"type":"content_block_stop","index":0}',
            '{"type":"message_delta",'
            '"delta":{"stop_reason":"end_turn"},'
            '"usage":{"output_tokens":5}}',
            "[DONE]",
        )
        result = _parse_sse_response(raw)
        assert result is not None
        assert result["id"] == "msg_1"
        assert result["model"] == "claude-sonnet-4-20250514"
        assert result["stop_reason"] == "end_turn"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello world"

    def test_empty_stream(self) -> None:
        assert _parse_sse_response("") is None

    def test_tool_use(self) -> None:
        import json

        msg_start = json.dumps(
            {
                "type": "message_start",
                "message": {
                    "id": "msg_2",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 10, "output_tokens": 0},
                },
            }
        )
        raw = _sse(
            msg_start,
            '{"type":"content_block_start","index":0,'
            '"content_block":{"type":"tool_use",'
            '"id":"tu_1","name":"search","input":{}}}',
            '{"type":"content_block_delta","index":0,'
            '"delta":{"type":"input_json_delta",'
            '"partial_json":"{\\"q\\""}}',
            '{"type":"content_block_delta","index":0,'
            '"delta":{"type":"input_json_delta",'
            '"partial_json":": \\"test\\"}"}}',
            '{"type":"content_block_stop","index":0}',
            '{"type":"message_delta",'
            '"delta":{"stop_reason":"tool_use"},'
            '"usage":{"output_tokens":20}}',
        )
        result = _parse_sse_response(raw)
        assert result is not None
        assert result["stop_reason"] == "tool_use"
        assert result["content"][0]["type"] == "tool_use"
        assert result["content"][0]["input"] == {"q": "test"}


# ---------------------------------------------------------------------------
# Proxy session integration tests
# ---------------------------------------------------------------------------


class TestProxySessionEnrich:
    def test_no_session_header_unchanged(self) -> None:
        """Without X-Session-Id, behavior is unchanged."""
        hooks = HookRegistry()
        enrich_mock = AsyncMock(return_value=None)
        hooks.register("session.enrich_request", enrich_mock, plugin_name="test")

        app = _make_app(hooks=hooks, session_service_url="http://localhost:9200")
        client = TestClient(app)

        mock_response = httpx.Response(
            200,
            json={"id": "msg_1", "content": [], "usage": {"input_tokens": 0, "output_tokens": 0}},
        )
        from unittest.mock import patch

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"x-api-key": "test-key"},
            )

        # Hook should NOT be called without X-Session-Id
        enrich_mock.assert_not_called()

    def test_session_header_emits_hook(self) -> None:
        """With X-Session-Id, the enrich hook is emitted."""
        hooks = HookRegistry()
        enrich_mock = AsyncMock(return_value=None)
        hooks.register("session.enrich_request", enrich_mock, plugin_name="test")
        save_mock = AsyncMock(return_value=None)
        hooks.register("session.save_response", save_mock, plugin_name="test")

        app = _make_app(hooks=hooks, session_service_url="http://localhost:9200")
        client = TestClient(app)

        mock_response = httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [{"type": "text", "text": "Hi!"}],
                "model": "claude-sonnet-4-20250514",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
        from unittest.mock import patch

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"x-api-key": "test-key", "x-session-id": "sess-123"},
            )

        # Enrich hook should be called
        enrich_mock.assert_called_once()
        call_kwargs = enrich_mock.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-123"
        assert call_kwargs["session_service_url"] == "http://localhost:9200"

        # Save hook should be called
        save_mock.assert_called_once()
        save_kwargs = save_mock.call_args.kwargs
        assert save_kwargs["session_id"] == "sess-123"

    def test_session_disabled_when_no_url(self) -> None:
        """With session_service_url=None, session hooks are not emitted."""
        hooks = HookRegistry()
        enrich_mock = AsyncMock(return_value=None)
        hooks.register("session.enrich_request", enrich_mock, plugin_name="test")

        app = _make_app(hooks=hooks, session_service_url=None)
        client = TestClient(app)

        mock_response = httpx.Response(
            200,
            json={"id": "msg_1", "content": [], "usage": {"input_tokens": 0, "output_tokens": 0}},
        )
        from unittest.mock import patch

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"x-api-key": "test-key", "x-session-id": "sess-123"},
            )

        # Hook should NOT be called when session_service_url is None
        enrich_mock.assert_not_called()

    def test_enrich_hook_failure_graceful(self) -> None:
        """If the enrich hook raises, the request still goes through."""
        hooks = HookRegistry()
        enrich_mock = AsyncMock(side_effect=RuntimeError("session service down"))
        hooks.register("session.enrich_request", enrich_mock, plugin_name="test")

        app = _make_app(hooks=hooks, session_service_url="http://localhost:9200")
        client = TestClient(app)

        mock_response = httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [{"type": "text", "text": "reply"}],
                "model": "claude-sonnet-4-20250514",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
        )
        from unittest.mock import patch

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            resp = client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"x-api-key": "test-key", "x-session-id": "sess-123"},
            )

        # Request should still succeed despite hook failure
        assert resp.status_code == 200
        assert resp.json()["content"][0]["text"] == "reply"
