# pyright: reportAttributeAccessIssue=false, reportOptionalSubscript=false, reportOperatorIssue=false
"""Unit tests for gemini-backend-api GeminiBackend.

Mocks the auth strategy and httpx so every test is hermetic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.gemini_backend_api.adapter import GeminiAdapter
from screamingface.plugins.gemini_backend_api.backend import (
    CODE_ASSIST_API_VERSION,
    CODE_ASSIST_ENDPOINT,
    GEMINI_API_BASE,
    GeminiBackend,
)
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _mock_auth(headers: dict[str, str], *, is_api_key: bool = False) -> MagicMock:
    """Build a fake GeminiAuth that returns the given headers."""
    auth = MagicMock()
    auth.get_authorization_header = AsyncMock(return_value=headers)
    auth.invalidate_cache = MagicMock()
    auth.is_api_key_auth = MagicMock(return_value=is_api_key)
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


def _sequenced_factory(*responses: httpx.Response) -> tuple[MagicMock, AsyncMock]:
    """Factory that returns different responses on successive calls."""
    call_count = {"n": 0}
    fake_client = AsyncMock()

    async def post(*args, **kwargs):
        resp = responses[min(call_count["n"], len(responses) - 1)]
        call_count["n"] += 1
        return resp

    fake_client.post.side_effect = post

    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_client)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm
    return factory, fake_client


def _api_key_success_response() -> httpx.Response:
    """Standard generativelanguage.googleapis.com response."""
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {"parts": [{"text": "pong"}], "role": "model"},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 5,
                "candidatesTokenCount": 1,
                "totalTokenCount": 6,
            },
        },
    )


def _code_assist_success_response() -> httpx.Response:
    """cloudcode-pa.googleapis.com response (Code Assist envelope)."""
    return httpx.Response(
        200,
        json={
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "pong"}], "role": "model"},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 6,
                },
            },
            "traceId": "trace-123",
        },
    )


def _load_code_assist_success() -> httpx.Response:
    """loadCodeAssist success response."""
    return httpx.Response(
        200,
        json={
            "cloudaicompanionProject": "test-project-abc",
            "currentTier": {"id": "free-tier", "name": "Gemini Code Assist for individuals"},
        },
    )


# ============================================================================
# API Key path tests
# ============================================================================


@pytest.mark.anyio
class TestApiKeyRunSuccessPath:
    async def test_success_returns_core_message(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(_api_key_success_response())
        backend = GeminiBackend(auth=auth, adapter=GeminiAdapter(), http_client_factory=factory)

        result = await backend.run(
            [CoreMessage(role="user", content="ping")],
            model="gemini-2.5-flash",
        )

        assert isinstance(result, CoreMessage)
        assert result.role == "assistant"
        assert isinstance(result.content[0], TextPart)
        assert result.content[0].text == "pong"

    async def test_posts_to_generativelanguage_url(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, fake_client = _mock_factory(_api_key_success_response())
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

        fake_client.post.assert_called_once()
        args, kwargs = fake_client.post.call_args
        assert GEMINI_API_BASE in args[0]
        assert "gemini-2.5-flash:generateContent" in args[0]

    async def test_includes_api_key_header(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, fake_client = _mock_factory(_api_key_success_response())
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

        args, kwargs = fake_client.post.call_args
        headers = kwargs["headers"]
        assert headers["x-goog-api-key"] == "test-key"
        assert headers["content-type"] == "application/json"


# ============================================================================
# OAuth / Code Assist path tests
# ============================================================================


@pytest.mark.anyio
class TestOAuthRunSuccessPath:
    async def test_success_returns_core_message(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, _ = _sequenced_factory(
            _load_code_assist_success(),
            _code_assist_success_response(),
        )
        backend = GeminiBackend(auth=auth, adapter=GeminiAdapter(), http_client_factory=factory)

        result = await backend.run(
            [CoreMessage(role="user", content="ping")],
            model="gemini-2.5-flash",
        )

        assert isinstance(result, CoreMessage)
        assert result.role == "assistant"
        assert result.content[0].text == "pong"

    async def test_posts_to_code_assist_url(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, fake_client = _sequenced_factory(
            _load_code_assist_success(),
            _code_assist_success_response(),
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

        # Second call is generateContent (first was loadCodeAssist)
        assert fake_client.post.call_count == 2
        generate_call = fake_client.post.call_args_list[1]
        url = generate_call.args[0]
        assert CODE_ASSIST_ENDPOINT in url
        assert f"{CODE_ASSIST_API_VERSION}:generateContent" in url

    async def test_wraps_request_in_code_assist_envelope(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, fake_client = _sequenced_factory(
            _load_code_assist_success(),
            _code_assist_success_response(),
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

        generate_call = fake_client.post.call_args_list[1]
        body = generate_call.kwargs["json"]
        assert body["model"] == "gemini-2.5-flash"
        assert body["project"] == "test-project-abc"
        assert "user_prompt_id" in body
        assert "request" in body
        assert "contents" in body["request"]
        assert "session_id" in body["request"]

    async def test_unwraps_code_assist_response_envelope(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, _ = _sequenced_factory(
            _load_code_assist_success(),
            _code_assist_success_response(),
        )
        backend = GeminiBackend(auth=auth, adapter=GeminiAdapter(), http_client_factory=factory)

        result = await backend.run(
            [CoreMessage(role="user", content="ping")], model="gemini-2.5-flash"
        )

        # Should have unwrapped the "response" envelope correctly
        assert result.content[0].text == "pong"
        assert result.provider_metadata["gemini.finish_reason"] == "STOP"

    async def test_calls_load_code_assist_on_first_request(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, fake_client = _sequenced_factory(
            _load_code_assist_success(),
            _code_assist_success_response(),
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

        # First call should be loadCodeAssist
        setup_call = fake_client.post.call_args_list[0]
        url = setup_call.args[0]
        assert "loadCodeAssist" in url
        body = setup_call.kwargs["json"]
        assert body["metadata"]["pluginType"] == "GEMINI"

    async def test_setup_cached_on_second_request(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, fake_client = _sequenced_factory(
            _load_code_assist_success(),
            _code_assist_success_response(),
            _code_assist_success_response(),
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")
        await backend.run(
            [CoreMessage(role="user", content="ping again")], model="gemini-2.5-flash"
        )

        # loadCodeAssist only once, generateContent twice
        urls = [call.args[0] for call in fake_client.post.call_args_list]
        assert sum("loadCodeAssist" in u for u in urls) == 1
        assert sum("generateContent" in u for u in urls) == 2


# ============================================================================
# Error path tests
# ============================================================================


@pytest.mark.anyio
class TestRunErrorPaths:
    async def test_429_with_retry_delay_retries(self):
        """429 with retryDelay causes automatic retry."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        error_body = {
            "error": {
                "code": 429,
                "message": "Rate limited",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "0.1s",
                    }
                ],
            }
        }
        factory, fake_client = _sequenced_factory(
            httpx.Response(429, json=error_body),
            _api_key_success_response(),
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        result = await backend.run(
            [CoreMessage(role="user", content="ping")], model="gemini-2.5-flash"
        )

        assert result.content[0].text == "pong"
        assert fake_client.post.call_count == 2

    async def test_429_exhausted_raises_backend_error(self):
        """Persistent 429 raises BackendError after max retries."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        error_body = {
            "error": {
                "code": 429,
                "message": "Rate limited",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "0.1s",
                    }
                ],
            }
        }
        resp = httpx.Response(429, json=error_body)
        factory, _ = _mock_factory(resp)
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError, match="rate limit") as exc_info:
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")
        assert exc_info.value.status == 429

    async def test_403_raises_auth_error(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(httpx.Response(403, json={"error": "forbidden"}))
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(AuthError, match="403"):
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

    async def test_500_raises_backend_error(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(httpx.Response(500, text="internal server error"))
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError) as exc_info:
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")
        assert exc_info.value.status == 500

    async def test_timeout_raises_backend_error(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.side_effect = httpx.ReadTimeout("too slow")
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError, match="timed out"):
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")


@pytest.mark.anyio
class TestRun401Recovery:
    async def test_single_401_recovered_by_retry(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _sequenced_factory(
            httpx.Response(401, json={"error": "expired"}),
            _api_key_success_response(),
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        result = await backend.run(
            [CoreMessage(role="user", content="ping")], model="gemini-2.5-flash"
        )

        auth.invalidate_cache.assert_called_once()
        assert result.content[0].text == "pong"

    async def test_double_401_raises_auth_error(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(httpx.Response(401, json={"error": "still bad"}))
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(AuthError, match="re-authenticate"):
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")


# ============================================================================
# Health check tests
# ============================================================================


@pytest.mark.anyio
class TestHealth:
    async def test_oauth_health_calls_load_code_assist(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, fake_client = _mock_factory(_load_code_assist_success())
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        status = await backend.health()

        assert status.authenticated is True
        assert status.error is None
        fake_client.post.assert_called_once()
        url = fake_client.post.call_args.args[0]
        assert "loadCodeAssist" in url

    async def test_api_key_health_calls_generate(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, fake_client = _mock_factory(_api_key_success_response())
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        status = await backend.health()

        assert status.authenticated is True
        fake_client.post.assert_called_once()
        url = fake_client.post.call_args.args[0]
        assert "generateContent" in url

    async def test_health_auth_failure(self):
        auth = MagicMock()
        auth.is_api_key_auth = MagicMock(return_value=False)
        auth.get_authorization_header = AsyncMock(side_effect=AuthError("No token found"))
        backend = GeminiBackend(auth=auth, http_client_factory=MagicMock())

        status = await backend.health()

        assert status.authenticated is False
        assert "No token found" in status.error

    async def test_health_rate_limited_429(self):
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(httpx.Response(429, json={"error": {"message": "Rate limited"}}))
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        status = await backend.health()

        assert status.authenticated is True
        assert "rate limited" in status.error

    async def test_health_network_failure(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.side_effect = httpx.ConnectError("Connection refused")
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = GeminiBackend(auth=auth, http_client_factory=factory)
        status = await backend.health()

        assert status.error is not None


# ============================================================================
# Code Assist setup error tests
# ============================================================================


@pytest.mark.anyio
class TestCodeAssistSetup:
    async def test_setup_failure_raises_backend_error(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)
        factory, _ = _mock_factory(httpx.Response(500, text="server error"))
        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError, match="loadCodeAssist"):
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")

    async def test_setup_network_error_raises_backend_error(self):
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)

        def factory():
            cm = MagicMock()
            fake_client = AsyncMock()
            fake_client.post.side_effect = httpx.ConnectError("no network")
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = GeminiBackend(auth=auth, http_client_factory=factory)

        with pytest.raises(BackendError, match="unreachable"):
            await backend.run([CoreMessage(role="user", content="ping")], model="gemini-2.5-flash")
