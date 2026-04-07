"""Tests for the claude-frontend proxy routes."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router
from screamingface.plugins.data_store.routes import _store as data_store_module_store
from screamingface.plugins.data_store.routes import get_blob


@pytest.fixture
def proxy_app() -> FastAPI:
    """Create a standalone FastAPI app with the proxy router (no full server startup)."""
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
    )
    app = FastAPI()
    router = create_router(settings)
    app.include_router(router)
    return app


@pytest.fixture
def proxy_client(proxy_app: FastAPI) -> TestClient:
    return TestClient(proxy_app)


def test_proxy_non_streaming(proxy_client: TestClient) -> None:
    mock_response = httpx.Response(
        200,
        json={"id": "msg_123", "content": [{"type": "text", "text": "Hello"}]},
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        resp = proxy_client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "msg_123"


def test_proxy_forwards_headers(proxy_client: TestClient) -> None:
    mock_response = httpx.Response(200, json={"id": "msg_456"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client.post(
            "/v1/messages",
            json={"model": "claude-sonnet-4-20250514", "messages": []},
            headers={
                "x-api-key": "sk-test",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "messages-2024-01-01",
            },
        )

    call_kwargs = mock_post.call_args
    sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert sent_headers["x-api-key"] == "sk-test"
    assert sent_headers["anthropic-version"] == "2023-06-01"
    assert sent_headers["anthropic-beta"] == "messages-2024-01-01"


def test_proxy_auth_fallback(proxy_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    mock_response = httpx.Response(200, json={"id": "msg_789"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client.post(
            "/v1/messages",
            json={"model": "claude-sonnet-4-20250514", "messages": []},
            # No x-api-key or authorization header
        )

    call_kwargs = mock_post.call_args
    sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert sent_headers["x-api-key"] == "sk-from-env"


# ----------------------------------------------------------------------------
# Filter integration tests — proxy stores filtered $prompt blob in data-store
# ----------------------------------------------------------------------------


class _StubPlugin:
    """Minimal plugin double for the proxy router.

    Only needs ``get_active_expression``; the proxy never calls
    ``resolve_context()`` when the expression contains ``$prompt``.
    """

    def __init__(self, expression: str) -> None:
        self._expression = expression

    def get_active_expression(self) -> str | None:
        return self._expression


def _make_filter_app(
    *, context_filter: list[str], expression: str = "($prompt)!'reflect'"
) -> FastAPI:
    """Build a proxy app wired up with a stub plugin and configured filter."""
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        context_filter=context_filter,
    )
    plugin = _StubPlugin(expression)
    app = FastAPI()
    router = create_router(settings, app=app, plugin=plugin, hooks=None)
    app.include_router(router)
    return app


def _multi_turn_body() -> dict[str, Any]:
    """Multi-turn request body with tool_use, tool_result, and a thinking block."""
    return {
        "model": "claude-opus-4-6",
        "max_tokens": 16000,
        "system": [{"type": "text", "text": "You are helpful."}],
        "tools": [
            {"name": "Bash", "description": "shell", "input_schema": {"type": "object"}},
        ],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "List python files."}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll list them."},
                    {
                        "type": "tool_use",
                        "id": "toolu_99",
                        "name": "Bash",
                        "input": {"command": "ls *.py"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_99",
                        "content": "alpha.py\nbeta.py\n",
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Two files.", "signature": "sig"},
                    {"type": "text", "text": "Found alpha.py and beta.py."},
                ],
            },
        ],
    }


@pytest.fixture(autouse=True)
def _clear_data_store():
    """Reset the in-process data store between tests."""
    data_store_module_store.clear()
    yield
    data_store_module_store.clear()


def _post_through_proxy(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    """POST a body to the proxy with the upstream Anthropic call mocked.

    Also patches Url4Interpreter so the proxy doesn't try to evaluate the
    spec expression for real — we only care about what gets stored in the
    blob, not the resolved url4 result.
    """
    upstream_response = httpx.Response(
        200,
        json={
            "id": "msg_xyz",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "model": "claude-opus-4-6",
            "stop_reason": "end_turn",
        },
    )

    # Stub Url4Interpreter so no real url4 evaluation is attempted; we only
    # care about what the proxy stored in the data-store, not the resolved
    # url4 result. The interpreter is constructed inside the proxy with
    # ``Url4Interpreter(app=app)`` so we patch the class to a callable that
    # returns an instance whose ``evaluate`` is an async coroutine.
    class _FakeInterpreter:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def evaluate(self, _expression: str) -> str:
            return "REFLECTED"

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=upstream_response
    ), patch(
        "screamingface.plugins.url4_executor.interpreter.Url4Interpreter",
        _FakeInterpreter,
    ):
        client = TestClient(app)
        return client.post(
            "/v1/messages",
            json=body,
            headers={"x-api-key": "sk-test", "anthropic-version": "2023-06-01"},
        )


def _stored_json_blobs() -> list[dict[str, Any]]:
    """Decode every JSON blob currently in the in-process data store."""
    blobs: list[dict[str, Any]] = []
    for key in list(data_store_module_store.keys()):
        entry = get_blob(key)
        assert entry is not None
        body, content_type = entry
        if content_type == "application/json":
            blobs.append(json.loads(body.decode("utf-8")))
    return blobs


def test_filter_default_user_text_stores_user_text_only() -> None:
    app = _make_filter_app(context_filter=["user:text"])
    resp = _post_through_proxy(app, _multi_turn_body())
    assert resp.status_code == 200

    blobs = _stored_json_blobs()
    assert len(blobs) == 1
    blob = blobs[0]
    assert "system" not in blob
    assert "tools" not in blob
    # Only user text blocks across all turns
    user_msgs = [m for m in blob.get("messages", []) if m["role"] == "user"]
    assert len(user_msgs) == 1  # turn 0 — turn 2 has only tool_result
    texts = [b["text"] for b in user_msgs[0]["content"]]
    assert texts == ["List python files."]
    # No assistant content
    assert all(m["role"] == "user" for m in blob["messages"])


def test_filter_reflection_includes_tool_calls_and_results() -> None:
    app = _make_filter_app(
        context_filter=["user:text,tool_result", "assistant:text,tool_call"]
    )
    resp = _post_through_proxy(app, _multi_turn_body())
    assert resp.status_code == 200

    blobs = _stored_json_blobs()
    assert len(blobs) == 1
    blob = blobs[0]

    user_blocks: list[dict[str, Any]] = []
    asst_blocks: list[dict[str, Any]] = []
    for msg in blob["messages"]:
        if msg["role"] == "user":
            user_blocks.extend(msg["content"])
        else:
            asst_blocks.extend(msg["content"])

    user_types = {b["type"] for b in user_blocks}
    asst_types = {b["type"] for b in asst_blocks}
    assert user_types == {"text", "tool_result"}
    assert asst_types == {"text", "tool_use"}
    # The tool_result content (file listing) is preserved verbatim
    tool_results = [b for b in user_blocks if b["type"] == "tool_result"]
    assert tool_results[0]["content"] == "alpha.py\nbeta.py\n"


def test_filter_full_dump_includes_system_and_tools() -> None:
    app = _make_filter_app(
        context_filter=["system:*", "tools:*", "user:*", "assistant:*"]
    )
    resp = _post_through_proxy(app, _multi_turn_body())
    assert resp.status_code == 200

    blobs = _stored_json_blobs()
    assert len(blobs) == 1
    blob = blobs[0]
    assert "system" in blob
    assert "tools" in blob
    assert blob["tools"][0]["name"] == "Bash"
    # All four messages survive
    assert len(blob["messages"]) == 4
    # Including the thinking block
    asst_types: set[str] = set()
    for msg in blob["messages"]:
        if msg["role"] == "assistant":
            asst_types.update(b["type"] for b in msg["content"])
    assert "thinking" in asst_types


def test_filter_empty_skips_blob_creation() -> None:
    app = _make_filter_app(context_filter=[])
    resp = _post_through_proxy(app, _multi_turn_body())
    assert resp.status_code == 200

    # No blobs at all (the proxy short-circuits before touching data-store)
    assert _stored_json_blobs() == []


def test_filter_assistant_tool_call_only() -> None:
    app = _make_filter_app(context_filter=["assistant:tool_call"])
    resp = _post_through_proxy(app, _multi_turn_body())
    assert resp.status_code == 200

    blobs = _stored_json_blobs()
    assert len(blobs) == 1
    blob = blobs[0]
    # Only one assistant message has tool_use, no user content
    assert all(m["role"] == "assistant" for m in blob["messages"])
    assert len(blob["messages"]) == 1
    types = {b["type"] for b in blob["messages"][0]["content"]}
    assert types == {"tool_use"}
    assert "system" not in blob
    assert "tools" not in blob


def test_filter_blob_is_application_json() -> None:
    """Confirm the stored blob has the right content-type for url4 fetch."""
    app = _make_filter_app(context_filter=["user:text"])
    _post_through_proxy(app, _multi_turn_body())

    keys = list(data_store_module_store.keys())
    assert len(keys) == 1
    _data, content_type = data_store_module_store[keys[0]]
    assert content_type == "application/json"
