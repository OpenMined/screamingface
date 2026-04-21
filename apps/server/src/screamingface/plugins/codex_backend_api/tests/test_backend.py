"""Unit tests for codex-backend-api OpenAIBackend.

Mocks the auth strategy and httpx so every test is hermetic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.codex_backend_api.backend import (
    OPENAI_RESPONSES_URL,
    OpenAIBackend,
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
    """Build a (factory, fake_client) pair."""
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
            "id": "resp_test",
            "object": "response",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "pong"}],
                }
            ],
            "model": "o4-mini",
            "status": "completed",
            "usage": {
                "input_tokens": 5,
                "output_tokens": 2,
                "total_tokens": 7,
            },
        },
    )


# ----------------------------------------------------------------------------
# Success path
# ----------------------------------------------------------------------------


class TestRunSuccess:
    @pytest.mark.anyio
    async def test_success_returns_core_message(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        factory, _ = _mock_factory(_success_response())
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        result = await backend.run(
            [CoreMessage(role="user", content=[TextPart(text="ping")])],
            model="o4-mini",
        )
        assert result.role == "assistant"
        assert isinstance(result.content, list)
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"

    @pytest.mark.anyio
    async def test_posts_to_correct_url(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        factory, fake_client = _mock_factory(_success_response())
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        await backend.run(
            [CoreMessage(role="user", content=[TextPart(text="ping")])],
            model="o4-mini",
        )
        call_args = fake_client.post.call_args
        assert call_args.args[0] == OPENAI_RESPONSES_URL

    @pytest.mark.anyio
    async def test_includes_auth_headers(self):
        auth = _mock_auth({"Authorization": "Bearer my-token"})
        factory, fake_client = _mock_factory(_success_response())
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        await backend.run(
            [CoreMessage(role="user", content=[TextPart(text="ping")])],
            model="o4-mini",
        )
        call_kwargs = fake_client.post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["content-type"] == "application/json"
        # No anthropic-specific headers
        assert "anthropic-version" not in headers


# ----------------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------------


class TestRunErrors:
    @pytest.mark.anyio
    async def test_429_raises_backend_error_with_retry_after(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        resp = httpx.Response(429, text="Rate limited", headers={"retry-after": "30"})
        factory, _ = _mock_factory(resp)
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError) as exc_info:
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="o4-mini",
            )
        assert exc_info.value.status == 429
        assert exc_info.value.retry_after == 30.0

    @pytest.mark.anyio
    async def test_403_raises_auth_error(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        factory, _ = _mock_factory(httpx.Response(403, text="Forbidden"))
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(AuthError, match="403 Forbidden"):
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="o4-mini",
            )

    @pytest.mark.anyio
    async def test_500_raises_backend_error(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        factory, _ = _mock_factory(httpx.Response(500, text="Server Error"))
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError) as exc_info:
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="o4-mini",
            )
        assert exc_info.value.status == 500

    @pytest.mark.anyio
    async def test_timeout_raises_backend_error(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})

        factory = MagicMock()
        cm = MagicMock()
        fake_client = AsyncMock()
        fake_client.post.side_effect = httpx.ReadTimeout("timed out")
        cm.__aenter__ = AsyncMock(return_value=fake_client)
        cm.__aexit__ = AsyncMock(return_value=None)
        factory.return_value = cm

        backend = OpenAIBackend(auth=auth, http_client_factory=factory)
        with pytest.raises(BackendError, match="timed out"):
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="o4-mini",
            )


# ----------------------------------------------------------------------------
# 401 retry
# ----------------------------------------------------------------------------


class TestRun401Recovery:
    @pytest.mark.anyio
    async def test_single_401_recovered_by_retry(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        resp_401 = httpx.Response(401, text="Unauthorized")

        call_count = 0

        async def _post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_401
            return _success_response()

        factory = MagicMock()
        cm = MagicMock()
        fake_client = AsyncMock()
        fake_client.post.side_effect = _post_side_effect
        cm.__aenter__ = AsyncMock(return_value=fake_client)
        cm.__aexit__ = AsyncMock(return_value=None)
        factory.return_value = cm

        backend = OpenAIBackend(auth=auth, http_client_factory=factory)
        result = await backend.run(
            [CoreMessage(role="user", content=[TextPart(text="ping")])],
            model="o4-mini",
        )
        assert isinstance(result.content, list)
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"
        auth.invalidate_cache.assert_called_once()

    @pytest.mark.anyio
    async def test_double_401_raises_auth_error(self):
        auth = _mock_auth({"Authorization": "Bearer tok"})
        factory, _ = _mock_factory(httpx.Response(401, text="Unauthorized"))
        backend = OpenAIBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(AuthError, match="twice in a row"):
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="o4-mini",
            )
