"""Tests for the ollama-frontend proxy routes."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.ollama_frontend.plugin import OllamaFrontendSettings
from screamingface.plugins.ollama_frontend.proxy import create_router


class _FakePlugin:
    """Minimal stand-in for OllamaFrontendPlugin in unit tests."""

    def __init__(self, expression: str | None = None, static_context: str | None = None) -> None:
        self._expression = expression
        self._static = static_context

    def get_active_expression(self) -> str | None:
        return self._expression

    def resolve_context(self) -> str | None:
        return self._static


def _app(settings: OllamaFrontendSettings, plugin: Any | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(create_router(settings, plugin=plugin))
    return app


def _ok_json(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=body)


def _default_ollama_body() -> dict[str, Any]:
    return {
        "model": "llama3",
        "created_at": "2026-04-20T12:00:00Z",
        "message": {"role": "assistant", "content": "Hello"},
        "done": True,
        "done_reason": "stop",
    }


# ---------------------------------------------------------------------------
# 1. Non-streaming passthrough, no spec
# ---------------------------------------------------------------------------


def test_non_streaming_passthrough_no_spec() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434")
    client = TestClient(_app(settings, plugin=_FakePlugin()))

    resp_body = _default_ollama_body()
    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok_json(resp_body)
    ) as mock_post:
        r = client.post(
            "/api/chat",
            json={
                "model": "llama3",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False,
            },
        )

    assert r.status_code == 200
    assert r.json()["message"]["content"] == "Hello"
    # Forwarded body unchanged (no injection)
    sent = mock_post.call_args.kwargs["json"]
    assert sent["messages"] == [{"role": "user", "content": "Hi"}]


# ---------------------------------------------------------------------------
# 2. Streaming NDJSON relay
# ---------------------------------------------------------------------------


def test_streaming_ndjson_relay() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434")
    client = TestClient(_app(settings, plugin=_FakePlugin()))

    chunks = [
        json.dumps(
            {"model": "llama3", "message": {"role": "assistant", "content": "He"}, "done": False}
        ).encode()
        + b"\n",
        json.dumps(
            {"model": "llama3", "message": {"role": "assistant", "content": "llo"}, "done": False}
        ).encode()
        + b"\n",
        json.dumps(
            {
                "model": "llama3",
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
            }
        ).encode()
        + b"\n",
    ]

    class _FakeStreamCtx:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.status_code = 200
            self.headers = httpx.Headers({"content-type": "application/x-ndjson"})

        async def __aenter__(self) -> _FakeStreamCtx:
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def aiter_bytes(self):
            for c in chunks:
                yield c

    with patch("httpx.AsyncClient.stream", lambda self, *a, **kw: _FakeStreamCtx()):
        with client.stream(
            "POST",
            "/api/chat",
            json={
                "model": "llama3",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("application/x-ndjson")
            relayed = b"".join(r.iter_bytes())

    assert relayed == b"".join(chunks)


# ---------------------------------------------------------------------------
# 3-5. Context injection variants
# ---------------------------------------------------------------------------


def test_inject_system_insert_when_absent() -> None:
    settings = OllamaFrontendSettings(
        upstream_url="http://localhost:11434",
        active_spec="dummy",
        embed_target="system",
        embed_mode="concat",
        system_prompt="SP",
    )
    plugin = _FakePlugin(expression="static-expr", static_context="CTX")
    client = TestClient(_app(settings, plugin=plugin))

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_ok_json(_default_ollama_body()),
    ) as mock_post:
        client.post(
            "/api/chat",
            json={
                "model": "llama3",
                "messages": [{"role": "user", "content": "Q"}],
                "stream": False,
            },
        )

    sent = mock_post.call_args.kwargs["json"]
    assert sent["messages"][0] == {"role": "system", "content": "SP\n\nCTX"}
    assert sent["messages"][1] == {"role": "user", "content": "Q"}


def test_inject_system_concat_with_existing() -> None:
    settings = OllamaFrontendSettings(
        upstream_url="http://localhost:11434",
        active_spec="dummy",
        embed_target="system",
        embed_mode="concat",
        system_prompt="SP",
    )
    plugin = _FakePlugin(expression="static-expr", static_context="CTX")
    client = TestClient(_app(settings, plugin=plugin))

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_ok_json(_default_ollama_body()),
    ) as mock_post:
        client.post(
            "/api/chat",
            json={
                "model": "llama3",
                "messages": [
                    {"role": "system", "content": "ORIG"},
                    {"role": "user", "content": "Q"},
                ],
                "stream": False,
            },
        )

    sent = mock_post.call_args.kwargs["json"]
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][0]["content"] == "SP\n\nCTX\n\nORIG"


def test_inject_user_replace() -> None:
    settings = OllamaFrontendSettings(
        upstream_url="http://localhost:11434",
        active_spec="dummy",
        embed_target="user",
        embed_mode="replace",
    )
    plugin = _FakePlugin(expression="static-expr", static_context="CTX")
    client = TestClient(_app(settings, plugin=plugin))

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_ok_json(_default_ollama_body()),
    ) as mock_post:
        client.post(
            "/api/chat",
            json={
                "model": "llama3",
                "messages": [{"role": "user", "content": "ORIGINAL"}],
                "stream": False,
            },
        )

    sent = mock_post.call_args.kwargs["json"]
    assert sent["messages"][0] == {"role": "user", "content": "CTX"}


# ---------------------------------------------------------------------------
# 6. $prompt spec: last user text substituted and resolved via /ensemble
# ---------------------------------------------------------------------------


def test_prompt_spec_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = OllamaFrontendSettings(
        upstream_url="http://localhost:11434",
        active_spec="with-prompt",
        backend_url="http://127.0.0.1:8000",
        embed_target="user",
        embed_mode="replace",
    )
    expression = "(https://docs.example.com, $prompt)!'answer'"
    plugin = _FakePlugin(expression=expression)
    client = TestClient(_app(settings, plugin=plugin))

    async def fake_post(self, url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        req = httpx.Request("POST", url)
        if url.endswith("/data"):
            return httpx.Response(200, json={"key": "abc123"}, request=req)
        return httpx.Response(200, json=_default_ollama_body(), request=req)

    captured_get: dict[str, Any] = {}

    async def fake_get(self, url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        captured_get["url"] = url
        captured_get["params"] = kwargs.get("params")
        return httpx.Response(200, text="RESOLVED_TEXT", request=httpx.Request("GET", url))

    with patch("httpx.AsyncClient.post", fake_post), patch("httpx.AsyncClient.get", fake_get):
        r = client.post(
            "/api/chat",
            json={
                "model": "llama3",
                "messages": [{"role": "user", "content": "what about cats?"}],
                "stream": False,
            },
        )

    assert r.status_code == 200
    # /ensemble was called with the substituted expression
    assert captured_get["url"].endswith("/ensemble")
    q = captured_get["params"]["q"]
    assert "/data/abc123" in q
    assert "$prompt" not in q


# ---------------------------------------------------------------------------
# 7. Header forwarding allowlist
# ---------------------------------------------------------------------------


def test_authorization_forwarded_other_stripped() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434")
    client = TestClient(_app(settings, plugin=_FakePlugin()))

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_ok_json(_default_ollama_body()),
    ) as mock_post:
        client.post(
            "/api/chat",
            json={"model": "llama3", "messages": [], "stream": False},
            headers={
                "Authorization": "Bearer sk-test",
                "X-Custom-Header": "leaked",
                "content-type": "application/json",
            },
        )

    sent_headers = mock_post.call_args.kwargs["headers"]
    assert sent_headers.get("authorization") == "Bearer sk-test"
    assert "x-custom-header" not in {k.lower() for k in sent_headers}


# ---------------------------------------------------------------------------
# 8. Catch-all passthrough (e.g. /api/tags)
# ---------------------------------------------------------------------------


def test_catchall_passthrough_tags() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434")
    client = TestClient(_app(settings, plugin=_FakePlugin()))

    tags_body = {"models": [{"name": "llama3:8b"}]}

    async def fake_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        assert method == "GET"
        assert url == "http://localhost:11434/api/tags"
        return httpx.Response(200, json=tags_body, headers={"content-type": "application/json"})

    with patch("httpx.AsyncClient.request", fake_request):
        r = client.get("/api/tags")

    assert r.status_code == 200
    assert r.json() == tags_body
