"""E2E tests for the claude-frontend TERMINAL inference path.

After the SF-240 terminal rewrite, ``POST /v1/messages`` resolves the active url4
spec in-process and synthesizes the Anthropic response envelope/stream itself — it
NEVER forwards inference to ``api.anthropic.com``. These tests drive a ``$prompt``
spec end-to-end with the real ``$prompt`` locus (``_store_prompt_blob`` /
``_resolve_expression``) mocked, and assert the synthesized response carries the
ensemble result with no upstream inference call.

(The previous httpbin live-server harness asserted url4 context injected into a
forwarded upstream request body; that behavior no longer exists, so it was removed.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def _prompt_plugin() -> MagicMock:
    """Plugin whose active spec contains the ``$prompt`` sentinel."""
    plugin = MagicMock()
    plugin.get_active_expression.return_value = '/claude($prompt)!"[end]" | /collect'
    return plugin


def test_e2e_prompt_spec_unary_no_upstream() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=_prompt_plugin()))
    client = TestClient(app)

    with (
        patch(
            "screamingface.plugins.claude_frontend._url4_context._store_prompt_blob",
            new_callable=AsyncMock,
            return_value="blob123",
        ),
        patch(
            "screamingface.plugins.claude_frontend._url4_context._resolve_expression",
            new_callable=AsyncMock,
            return_value="Ensemble answer: the test passed",
        ),
        patch("httpx.AsyncClient") as mock_client,
    ):
        resp = client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "What is 2+2?"}],
            },
        )

    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "Ensemble answer: the test passed"
    assert not mock_client.called or all(
        "api.anthropic.com" not in str(c) for c in mock_client.call_args_list
    )


def test_e2e_prompt_spec_streaming_no_upstream() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=_prompt_plugin()))
    client = TestClient(app)

    with (
        patch(
            "screamingface.plugins.claude_frontend._url4_context._store_prompt_blob",
            new_callable=AsyncMock,
            return_value="blob123",
        ),
        patch(
            "screamingface.plugins.claude_frontend._url4_context._resolve_expression",
            new_callable=AsyncMock,
            return_value="Streamed result",
        ),
        patch("httpx.AsyncClient.stream") as mock_stream,
    ):
        resp = client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "Stream this"}],
                "stream": True,
            },
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "message_stop" in resp.text
    assert "Streamed result" in resp.text
    assert not mock_stream.called


def test_e2e_prompt_spec_full_transcript_blob() -> None:
    """Decision A: the $prompt blob is the FULL serialized transcript (all turns)."""
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=_prompt_plugin()))
    client = TestClient(app)

    store_mock = AsyncMock(return_value="blob123")
    with (
        patch(
            "screamingface.plugins.claude_frontend._url4_context._store_prompt_blob",
            store_mock,
        ),
        patch(
            "screamingface.plugins.claude_frontend._url4_context._resolve_expression",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        resp = client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-1-20250805",
                "messages": [
                    {"role": "user", "content": "first question"},
                    {"role": "assistant", "content": "first answer"},
                    {"role": "user", "content": "second question"},
                ],
            },
        )

    assert resp.status_code == 200
    assert store_mock.await_args is not None
    stored_text = store_mock.await_args.args[0]
    assert "User: first question" in stored_text
    assert "Assistant: first answer" in stored_text
    assert "User: second question" in stored_text
