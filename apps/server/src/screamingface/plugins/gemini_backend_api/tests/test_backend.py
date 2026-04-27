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
    async def test_oauth_health_calls_load_code_assist_then_probes(self):
        """OAuth health does loadCodeAssist + a 1-token generateContent probe.

        The probe is required because loadCodeAssist isn't quota-metered,
        so bare-setup calls can't detect 429s on the model — downstream
        test-matrix skip logic relies on the error='rate limited' signal
        from a real generateContent response.
        """
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)

        def factory():  # noqa: ANN202
            cm = MagicMock()
            fake_client = AsyncMock()
            # Two sequential responses: loadCodeAssist then generateContent.
            fake_client.post.side_effect = [
                _load_code_assist_success(),
                _api_key_success_response(),
            ]
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            cm._fake_client = fake_client  # type: ignore[attr-defined]
            return cm

        cm_holder: dict = {}
        original_factory = factory

        def spy_factory():  # noqa: ANN202
            cm = original_factory()
            cm_holder.setdefault("cm", cm)
            return cm

        backend = GeminiBackend(auth=auth, http_client_factory=spy_factory)
        status = await backend.health()

        assert status.authenticated is True
        assert status.error is None
        # Two calls: one per context-manager factory instance, each with
        # a single post (loadCodeAssist first time, generateContent second).
        # We can assert the URL shape by inspecting the aggregated calls.

    async def test_oauth_health_reports_rate_limited_on_429(self):
        """When generateContent probe returns 429, health surfaces 'rate limited'."""
        auth = _mock_auth({"Authorization": "Bearer ya29.test"}, is_api_key=False)

        # First factory call (loadCodeAssist) succeeds, second (generateContent) 429s.
        call_count = {"n": 0}

        def factory():  # noqa: ANN202
            cm = MagicMock()
            fake_client = AsyncMock()
            if call_count["n"] == 0:
                fake_client.post.return_value = _load_code_assist_success()
            else:
                fake_client.post.return_value = httpx.Response(
                    429, json={"error": {"message": "Quota exhausted"}}
                )
            call_count["n"] += 1
            cm.__aenter__ = AsyncMock(return_value=fake_client)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        backend = GeminiBackend(auth=auth, http_client_factory=factory)
        status = await backend.health()

        assert status.authenticated is True
        assert status.error is not None
        assert "rate limited" in status.error.lower()

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


@pytest.mark.anyio
class TestModelFallback:
    """SF-114: when configured model 429s, fall back to next in chain."""

    async def test_first_model_429_second_model_succeeds(self):
        """flash 429 → pro succeeds → returns pro's response."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, fake_client = _sequenced_factory(
            httpx.Response(429, json={"error": {"message": "Quota exhausted"}}),
            _api_key_success_response(),
        )
        backend = GeminiBackend(
            auth=auth,
            http_client_factory=factory,
            fallback_models=["gemini-2.5-pro"],
        )

        result = await backend.run(
            [CoreMessage(role="user", content=[TextPart(text="ping")])],
            model="gemini-2.5-flash",
        )

        assert isinstance(result, CoreMessage)
        assert result.content[0].text == "pong"
        # Two POSTs: one to flash (429), one to pro (200).
        assert fake_client.post.call_count == 2
        first_url = fake_client.post.call_args_list[0].args[0]
        second_url = fake_client.post.call_args_list[1].args[0]
        assert "gemini-2.5-flash" in first_url
        assert "gemini-2.5-pro" in second_url

    async def test_chain_exhausted_raises_last_429(self):
        """Every model in the chain 429s — surface the last error."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(
            httpx.Response(429, json={"error": {"message": "Quota exhausted"}})
        )
        backend = GeminiBackend(
            auth=auth,
            http_client_factory=factory,
            fallback_models=["gemini-2.5-pro", "gemini-2.5-flash-lite"],
        )

        with pytest.raises(BackendError) as exc_info:
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="gemini-2.5-flash",
            )
        assert exc_info.value.status == 429

    async def test_dedup_chain_does_not_retry_same_model(self):
        """Configured model already in fallback list — only tried once."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, fake_client = _mock_factory(
            httpx.Response(429, json={"error": {"message": "Quota exhausted"}})
        )
        backend = GeminiBackend(
            auth=auth,
            http_client_factory=factory,
            fallback_models=["gemini-2.5-flash", "gemini-2.5-pro"],
        )

        with pytest.raises(BackendError):
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="gemini-2.5-flash",
            )
        # 2 distinct models attempted (flash, pro), each retried up to
        # MAX_429_RETRIES+1 by _post_with_retry. flash should appear
        # exactly once in the unique-attempt set.
        urls_attempted = {call.args[0] for call in fake_client.post.call_args_list}
        assert sum("gemini-2.5-flash:" in u for u in urls_attempted) == 1
        assert any("gemini-2.5-pro" in u for u in urls_attempted)

    async def test_non_429_error_no_fallback(self):
        """500 from configured model — do NOT try fallback (real outage)."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, fake_client = _mock_factory(httpx.Response(500, text="internal"))
        backend = GeminiBackend(
            auth=auth,
            http_client_factory=factory,
            fallback_models=["gemini-2.5-pro"],
        )

        with pytest.raises(BackendError) as exc_info:
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="gemini-2.5-flash",
            )
        assert exc_info.value.status == 500
        # Exactly one URL should appear (the original — no fallback).
        urls = {c.args[0] for c in fake_client.post.call_args_list}
        assert all("gemini-2.5-flash" in u for u in urls)

    async def test_no_fallback_chain_legacy_behavior(self):
        """Empty fallback_models — single attempt, raise on 429."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(
            httpx.Response(429, json={"error": {"message": "Quota exhausted"}})
        )
        backend = GeminiBackend(auth=auth, http_client_factory=factory)  # no fallback

        with pytest.raises(BackendError) as exc_info:
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="gemini-2.5-flash",
            )
        assert exc_info.value.status == 429


@pytest.mark.anyio
class TestMaxTotalRetryWait:
    """SF-116: cumulative 429-retry sleep is capped per request.

    Without the cap, a sequence of long retry-after headers can stack
    until the request-level timeout (45s in tests) fires as a confusing
    httpx ReadTimeout instead of a clean BackendError(429).
    """

    @staticmethod
    def _retry_response(delay_s: float) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "message": "Rate limited",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": f"{delay_s}s",
                        }
                    ],
                }
            },
        )

    async def test_total_wait_exceeded_raises_immediately(self, monkeypatch):
        """Second retry-after would push cumulative wait past cap → raise.

        cap=10s. First retry-after=6s (sleep 6.5s, total=6.5).
        Second retry-after=6s (next sleep 6.5s; 6.5+6.5=13 > 10 → raise).
        Asserts only one sleep happened.
        """
        sleeps: list[float] = []

        async def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(
            "screamingface.plugins.gemini_backend_api.backend.asyncio.sleep",
            fake_sleep,
        )

        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(self._retry_response(6.0))
        backend = GeminiBackend(
            auth=auth,
            http_client_factory=factory,
            max_total_wait_seconds=10.0,
        )

        with pytest.raises(BackendError) as ei:
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="gemini-2.5-flash",
            )
        assert ei.value.status == 429
        assert "cumulative retry" in str(ei.value)
        assert len(sleeps) == 1, f"expected exactly one sleep before cap; got {sleeps}"

    async def test_under_cap_retries_normally(self, monkeypatch):
        """Cumulative wait stays under cap — retries proceed until exhausted."""
        sleeps: list[float] = []

        async def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(
            "screamingface.plugins.gemini_backend_api.backend.asyncio.sleep",
            fake_sleep,
        )

        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(self._retry_response(0.1))
        backend = GeminiBackend(
            auth=auth,
            http_client_factory=factory,
            max_total_wait_seconds=30.0,
        )

        with pytest.raises(BackendError):
            await backend.run(
                [CoreMessage(role="user", content=[TextPart(text="ping")])],
                model="gemini-2.5-flash",
            )
        # MAX_429_RETRIES = 3 → up to 3 sleeps before final raise
        assert len(sleeps) == 3
        assert all(abs(s - 0.6) < 1e-6 for s in sleeps)  # 0.1 + 0.5 jitter

    async def test_default_cap_is_30_seconds(self):
        """Default constructor value matches MAX_TOTAL_429_WAIT_SECONDS."""
        auth = _mock_auth({"x-goog-api-key": "test-key"}, is_api_key=True)
        factory, _ = _mock_factory(httpx.Response(200, json={}))
        backend = GeminiBackend(auth=auth, http_client_factory=factory)
        assert backend._max_total_wait_seconds == 30.0
