"""Unit tests for OllamaBackend — httpx transport, status-code handling."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart
from screamingface.plugins.ollama_backend_api.auth import OllamaAuth
from screamingface.plugins.ollama_backend_api.backend import OllamaBackend

pytestmark = pytest.mark.anyio


def _ping_messages() -> list[CoreMessage]:
    return [CoreMessage(role="user", content=[TextPart(text="ping")])]


def _success_response(text: str = "pong") -> httpx.Response:
    """Return a 200 httpx.Response bound to a fake request so raise_for_status works."""
    req = httpx.Request("POST", "http://localhost:11434/api/chat")
    body = {
        "model": "llama3",
        "created_at": "2026-04-23T00:00:00Z",
        "message": {"role": "assistant", "content": text},
        "done": True,
        "done_reason": "stop",
    }
    return httpx.Response(200, json=body, request=req)


def _status_response(status: int, body: dict[str, Any] | None = None) -> httpx.Response:
    req = httpx.Request("POST", "http://localhost:11434/api/chat")
    return httpx.Response(status, json=body or {"error": "x"}, request=req)


class _FakeAsyncClient:
    """Minimal async-context-manager replacement for httpx.AsyncClient.

    Records the last POST and returns canned responses in order. Also
    supports GET for health() tests.
    """

    def __init__(self, post_responses: list[httpx.Response]):
        self._post_responses = list(post_responses)
        self.post_calls: list[dict[str, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object):
        return None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]):
        self.post_calls.append({"url": url, "json": json, "headers": headers})
        return self._post_responses.pop(0)

    async def get(self, url: str, *, headers: dict[str, str]):
        return self._post_responses.pop(0)


def _factory(client: _FakeAsyncClient):
    def make():
        return client

    return make


# ----------------------------------------------------------------------------
# run() — happy paths
# ----------------------------------------------------------------------------


class TestRunSuccess:
    async def test_posts_to_chat_url_with_stream_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_success_response()])
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            auth=OllamaAuth(),
            http_client_factory=_factory(client),
        )

        result = await backend.run(_ping_messages(), model="llama3")

        assert len(client.post_calls) == 1
        call = client.post_calls[0]
        assert call["url"] == "http://localhost:11434/api/chat"
        assert call["json"]["model"] == "llama3"
        assert call["json"]["stream"] is False
        assert call["json"]["messages"] == [{"role": "user", "content": "ping"}]
        assert "Authorization" not in call["headers"]

        assert result.role == "assistant"
        assert isinstance(result.content, list)
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"

    async def test_base_url_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_success_response()])
        backend = OllamaBackend(
            base_url="http://localhost:11434///",
            auth=OllamaAuth(),
            http_client_factory=_factory(client),
        )
        await backend.run(_ping_messages(), model="llama3")
        assert client.post_calls[0]["url"] == "http://localhost:11434/api/chat"

    async def test_bearer_header_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_success_response()])
        backend = OllamaBackend(
            auth=OllamaAuth(api_key="tok"), http_client_factory=_factory(client)
        )
        await backend.run(_ping_messages(), model="llama3")
        assert client.post_calls[0]["headers"]["Authorization"] == "Bearer tok"


# ----------------------------------------------------------------------------
# run() — error paths
# ----------------------------------------------------------------------------


class TestRunErrors:
    async def test_401_then_401_raises_auth_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_status_response(401), _status_response(401)])
        backend = OllamaBackend(
            auth=OllamaAuth(api_key="bad"), http_client_factory=_factory(client)
        )
        with pytest.raises(AuthError, match="Authentication failed twice"):
            await backend.run(_ping_messages(), model="llama3")
        assert len(client.post_calls) == 2

    async def test_401_then_200_retries_and_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_status_response(401), _success_response("pong")])
        backend = OllamaBackend(
            auth=OllamaAuth(api_key="rotated"), http_client_factory=_factory(client)
        )
        result = await backend.run(_ping_messages(), model="llama3")
        assert len(client.post_calls) == 2
        assert isinstance(result.content, list)
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"

    async def test_429_raises_backend_error_with_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_status_response(429)])
        backend = OllamaBackend(auth=OllamaAuth(), http_client_factory=_factory(client))
        with pytest.raises(BackendError) as exc_info:
            await backend.run(_ping_messages(), model="llama3")
        assert exc_info.value.status == 429

    async def test_404_hints_at_model_pull(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_status_response(404)])
        backend = OllamaBackend(auth=OllamaAuth(), http_client_factory=_factory(client))
        with pytest.raises(BackendError, match="ollama pull"):
            await backend.run(_ping_messages(), model="not-installed")

    async def test_500_raises_backend_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = _FakeAsyncClient([_status_response(500)])
        backend = OllamaBackend(auth=OllamaAuth(), http_client_factory=_factory(client))
        with pytest.raises(BackendError) as exc_info:
            await backend.run(_ping_messages(), model="llama3")
        assert exc_info.value.status == 500


# ----------------------------------------------------------------------------
# health()
# ----------------------------------------------------------------------------


class TestHealth:
    async def test_200_means_authenticated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        req = httpx.Request("GET", "http://localhost:11434/api/tags")
        tags_ok = httpx.Response(200, json={"models": []}, request=req)
        client = _FakeAsyncClient([tags_ok])
        backend = OllamaBackend(auth=OllamaAuth(), http_client_factory=_factory(client))
        status = await backend.health()
        assert status.authenticated is True
        assert status.error is None

    async def test_401_means_unauthenticated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        req = httpx.Request("GET", "http://localhost:11434/api/tags")
        tags_401 = httpx.Response(401, json={"error": "nope"}, request=req)
        client = _FakeAsyncClient([tags_401])
        backend = OllamaBackend(
            auth=OllamaAuth(api_key="bad"), http_client_factory=_factory(client)
        )
        status = await backend.health()
        assert status.authenticated is False
        assert status.error is not None and "401" in status.error
