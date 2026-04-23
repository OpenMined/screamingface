"""AnthropicBackend — raw httpx POST to api.anthropic.com/v1/messages.

Wires the three pieces of the provider stack together:

1. :class:`~claude_backend_api.auth.ClaudeCodeOAuth` builds the headers
   (OAuth bearer + ``anthropic-version`` + ``anthropic-beta``).
2. :class:`~claude_backend_api.adapter.AnthropicAdapter` converts the
   incoming :class:`CoreMessage` list into an Anthropic Messages API
   request body and parses the response back.
3. This module does the transport: ``httpx.AsyncClient.post()`` to
   ``https://api.anthropic.com/v1/messages``, handles status codes,
   one-shot 401 retry path via auth cache invalidation.

No streaming yet — Phase 1 is non-streaming only. Streaming comes in a
follow-up ticket and lives on a separate ``stream()`` method so the
simple path stays simple.
"""

from __future__ import annotations

import logging

import httpx

from screamingface.plugins.claude_backend_api.adapter import AnthropicAdapter
from screamingface.plugins.claude_backend_api.auth import ClaudeCodeOAuth
from screamingface.plugins.llm_base.backend_base import (
    Backend,
    HealthStatus,
    post_with_default_retry,
)
from screamingface.plugins.llm_base.http import default_http_factory
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages?beta=true"


class AnthropicBackend(Backend):
    """Direct-to-API backend for Anthropic's Messages endpoint.

    Args:
        auth: The auth strategy to build headers with. Defaults to
            :class:`ClaudeCodeOAuth` using the platform credential store.
        adapter: The shape adapter to use. Defaults to
            :class:`AnthropicAdapter`.
        http_client_factory: Callable returning an ``httpx.AsyncClient``.
            Tests inject a factory that returns a mocked client.
    """

    def __init__(
        self,
        *,
        auth: ClaudeCodeOAuth | None = None,
        adapter: AnthropicAdapter | None = None,
        http_client_factory=None,
    ) -> None:
        self._auth = auth or ClaudeCodeOAuth()
        self._adapter = adapter or AnthropicAdapter()
        self._http_factory = http_client_factory or default_http_factory

    async def health(self, model: str = "claude-haiku-4-5") -> HealthStatus:
        """Check auth validity and rate limit capacity.

        Args:
            model: The configured default model. The probe tries this
                model first; if it's rate-limited, falls back to
                claude-haiku-4-5 to confirm auth still works.

        The backend is reported as ``authenticated=True`` if ANY model
        responds (even if the configured one is rate-limited). The
        ``error`` field describes which model is limited.
        """
        # Step 1: check auth (credential exists + not expired)
        try:
            headers = await self._auth.get_authorization_header()
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        # Step 2: probe the configured model
        result = await self._probe_model(headers, model)
        if result.authenticated and result.error is None:
            return result  # configured model works

        # Step 3: if configured model is rate-limited, try haiku fallback
        if result.authenticated and result.error and "rate limited" in result.error:
            fallback = "claude-haiku-4-5"
            if model != fallback:
                fallback_result = await self._probe_model(headers, fallback)
                if fallback_result.authenticated and fallback_result.error is None:
                    # Auth works, configured model is rate-limited but fallback is available
                    return HealthStatus(
                        authenticated=True,
                        error=f"{model} rate limited, {fallback} available",
                        tokens_remaining=fallback_result.tokens_remaining,
                        requests_remaining=fallback_result.requests_remaining,
                        rate_limit={
                            **fallback_result.rate_limit,
                            "limited_model": model,
                            "available_model": fallback,
                        },
                    )

        return result

    async def _probe_model(self, headers: dict[str, str], model: str) -> HealthStatus:
        """Make a minimal 1-token API call to check a specific model."""
        from screamingface.plugins.claude_backend_api.adapter import _build_billing_header

        probe_headers = {**headers, "content-type": "application/json"}
        billing = _build_billing_header("hi")
        body = {
            "model": model,
            "max_tokens": 1,
            "system": [{"type": "text", "text": billing}],
            "messages": [{"role": "user", "content": "hi"}],
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(ANTHROPIC_MESSAGES_URL, json=body, headers=probe_headers)
        except Exception as exc:
            return HealthStatus(authenticated=True, error=f"API unreachable: {exc}")

        rate_limit = _extract_rate_limits(resp.headers)
        tokens_remaining = rate_limit.get("tokens_remaining")
        requests_remaining = rate_limit.get("requests_remaining")

        if resp.status_code == 200:
            return HealthStatus(
                authenticated=True,
                tokens_remaining=int(tokens_remaining) if tokens_remaining is not None else None,
                requests_remaining=(
                    int(requests_remaining) if requests_remaining is not None else None
                ),
                rate_limit=rate_limit,
            )

        if resp.status_code == 429:
            return HealthStatus(
                authenticated=True,
                error=f"rate limited on {model}",
                tokens_remaining=int(tokens_remaining) if tokens_remaining is not None else None,
                requests_remaining=(
                    int(requests_remaining) if requests_remaining is not None else None
                ),
                rate_limit=rate_limit,
            )

        if resp.status_code in (401, 403):
            return HealthStatus(
                authenticated=False,
                error=f"API rejected token (HTTP {resp.status_code}): {resp.text[:300]}",
            )

        return HealthStatus(
            authenticated=True,
            error=f"Unexpected API status {resp.status_code}: {resp.text[:300]}",
            rate_limit=rate_limit,
        )

    async def run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 16000,
        temperature: float | None = None,
        timeout_seconds: float = 300.0,
    ) -> CoreMessage:
        """Execute one non-streaming round-trip against Anthropic.

        Flow:

        1. Build the outbound request body via the adapter.
        2. Get auth headers from :class:`ClaudeCodeOAuth`.
        3. POST to ``/v1/messages``.
        4. On 401: invalidate auth cache, retry exactly once.
        5. On 200: parse via the adapter, return the CoreMessage.
        6. On any other error status: raise :class:`BackendError` with
           the status code and, when present, ``retry-after`` header.
        """
        body = self._adapter.to_provider_format(
            messages,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        response_data = await self._post_with_retry(body)
        return self._adapter.from_provider_response(response_data)

    async def _post_with_retry(self, body: dict) -> dict:
        """Delegate to the shared POST-with-401-retry helper."""
        return await post_with_default_retry(
            auth=self._auth,
            http_factory=self._http_factory,
            url=ANTHROPIC_MESSAGES_URL,
            body=body,
            provider_name="Anthropic",
            auth_login_cmd="claude auth login",
        )


def _extract_rate_limits(headers: httpx.Headers) -> dict[str, str | int | float]:
    """Extract Anthropic rate limit headers into a flat dict.

    Anthropic returns headers like::

        anthropic-ratelimit-tokens-limit: 80000
        anthropic-ratelimit-tokens-remaining: 79950
        anthropic-ratelimit-tokens-reset: 2024-01-01T00:00:00Z
        anthropic-ratelimit-requests-limit: 50
        anthropic-ratelimit-requests-remaining: 49
        anthropic-ratelimit-requests-reset: 2024-01-01T00:00:00Z

    We normalize these to short keys.
    """
    prefix = "anthropic-ratelimit-"
    result: dict[str, str | int | float] = {}
    for key, value in headers.items():
        if key.lower().startswith(prefix):
            short_key = key[len(prefix) :].replace("-", "_")
            try:
                result[short_key] = int(value)
            except ValueError:
                try:
                    result[short_key] = float(value)
                except ValueError:
                    result[short_key] = value
    return result
