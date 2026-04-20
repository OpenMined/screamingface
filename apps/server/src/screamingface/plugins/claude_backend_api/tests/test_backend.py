"""Unit tests for claude-backend-api AnthropicBackend.

Mocks the auth strategy and httpx so every test is hermetic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.claude_backend_api.adapter import AnthropicAdapter
from screamingface.plugins.claude_backend_api.backend import (
    ANTHROPIC_MESSAGES_URL,
    AnthropicBackend,
)
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart


def _mock_auth(headers: dict[str, str]) -> MagicMock:
    """Build a fake AuthStrategy that returns the given headers."""
    auth = MagicMock()
    auth.get_authorization_header = AsyncMock(return_value=headers)
    auth.invalidate_cache = MagicMock()
    return auth


def _mock_factory(response: httpx.Response) -> tuple[MagicMock, AsyncMock]:
    """Build a (factory, fake_client) pair. Same shape as test_auth."""
    fake_client = AsyncMock()
    fake_client.post.return_value = response

    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_client)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm
    return factory, fake_client


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "pong"}],
            "model": "claude-sonnet-4-5",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 1},
        },
    )


@pytest.mark.anyio
class TestRunSuccessPath:
    async def test_success_returns_core_message(self):
        auth = _mock_auth(
            {
                "Authorization": "Bearer sk-test",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "oauth-2025-04-20",
            }
        )
        factory, _ = _mock_factory(_success_response())
        backend = AnthropicBackend(
            auth=auth, adapter=AnthropicAdapter(), http_client_factory=factory
        )

        result = await backend.run(
            [CoreMessage(role="user", content="ping")],
            model="claude-sonnet-4-5",
        )

        assert isinstance(result, CoreMessage)
        assert result.role == "assistant"
        assert isinstance(result.content, list)
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"

    async def test_posts_to_correct_url(self):
        auth = _mock_auth({"Authorization": "Bearer sk-test"})
        factory, fake_client = _mock_factory(_success_response())
        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="claude-sonnet-4-5")

        fake_client.post.assert_called_once()
        args, kwargs = fake_client.post.call_args
        assert args[0] == ANTHROPIC_MESSAGES_URL

    async def test_includes_auth_headers(self):
        auth = _mock_auth(
            {
                "Authorization": "Bearer sk-test",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "oauth-2025-04-20",
            }
        )
        factory, fake_client = _mock_factory(_success_response())
        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="claude-sonnet-4-5")

        args, kwargs = fake_client.post.call_args
        headers = kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["anthropic-beta"] == "oauth-2025-04-20"
        assert headers["content-type"] == "application/json"

    async def test_passes_model_and_system_to_body(self):
        auth = _mock_auth({"Authorization": "Bearer sk-test"})
        factory, fake_client = _mock_factory(_success_response())
        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="claude-opus-4",
            system="You are helpful.",
        )

        args, kwargs = fake_client.post.call_args
        body = kwargs["json"]
        assert body["model"] == "claude-opus-4"
        assert body["system"] == "You are helpful."


@pytest.mark.anyio
class TestRunErrorPaths:
    async def test_429_raises_backend_error_with_retry_after(self):
        auth = _mock_auth({"Authorization": "Bearer sk-test"})
        factory, _ = _mock_factory(
            httpx.Response(
                429,
                json={"type": "error", "error": {"type": "rate_limit_error"}},
                headers={"retry-after": "60"},
            )
        )
        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError, match="rate limit") as exc_info:
            await backend.run(
                [CoreMessage(role="user", content="ping")],
                model="claude-sonnet-4-5",
            )

        assert exc_info.value.status == 429
        assert exc_info.value.retry_after == 60.0

    async def test_403_raises_auth_error(self):
        auth = _mock_auth({"Authorization": "Bearer sk-test"})
        factory, _ = _mock_factory(httpx.Response(403, json={"error": "forbidden"}))
        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(AuthError, match="403"):
            await backend.run(
                [CoreMessage(role="user", content="ping")],
                model="claude-sonnet-4-5",
            )

    async def test_500_raises_backend_error(self):
        auth = _mock_auth({"Authorization": "Bearer sk-test"})
        factory, _ = _mock_factory(httpx.Response(500, text="internal server error"))
        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError) as exc_info:
            await backend.run(
                [CoreMessage(role="user", content="ping")],
                model="claude-sonnet-4-5",
            )
        assert exc_info.value.status == 500

    async def test_timeout_raises_backend_error(self):
        auth = _mock_auth({"Authorization": "Bearer sk-test"})

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.side_effect = httpx.ReadTimeout("too slow")
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError, match="timed out"):
            await backend.run(
                [CoreMessage(role="user", content="ping")],
                model="claude-sonnet-4-5",
            )


@pytest.mark.anyio
class TestRun401Recovery:
    async def test_single_401_recovered_by_retry(self):
        """First POST returns 401; backend invalidates cache, retries,
        second POST returns 200. Caller sees success."""
        auth = _mock_auth({"Authorization": "Bearer sk-test"})

        # httpx.Response objects, in order returned by the mock
        responses = [
            httpx.Response(401, json={"error": "expired"}),
            _success_response(),
        ]
        call_count = {"n": 0}

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()

            async def post(*args, **kwargs):
                resp = responses[call_count["n"]]
                call_count["n"] += 1
                return resp

            fake_client.post.side_effect = post
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = AnthropicBackend(auth=auth, http_client_factory=factory)
        result = await backend.run(
            [CoreMessage(role="user", content="ping")], model="claude-sonnet-4-5"
        )

        assert call_count["n"] == 2
        auth.invalidate_cache.assert_called_once()
        assert isinstance(result.content, list)
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"

    async def test_double_401_raises_auth_error(self):
        """Two consecutive 401s mean the credential is actually bad."""
        auth = _mock_auth({"Authorization": "Bearer sk-test"})

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.return_value = httpx.Response(401, json={"error": "still expired"})
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = AnthropicBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(AuthError, match="twice in a row"):
            await backend.run(
                [CoreMessage(role="user", content="ping")],
                model="claude-sonnet-4-5",
            )
