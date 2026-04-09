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
import ssl

import certifi
import httpx

from screamingface.plugins.claude_backend_api.adapter import AnthropicAdapter
from screamingface.plugins.claude_backend_api.auth import ClaudeCodeOAuth
from screamingface.plugins.llm_base.backend_base import Backend
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


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
        # Lazy-construct the SSL context so import-time failures don't
        # block plugin loading. certifi.where() does a disk read.
        self._http_factory = http_client_factory or self._default_http_factory

    @staticmethod
    def _default_http_factory():
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            verify=ssl_ctx,
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
        """POST with the one-shot 401-retry recovery path.

        Called with an already-built request body. Handles auth header
        construction, the upstream POST, and the 401→invalidate→retry
        cycle. Returns the parsed response dict on success.
        """
        # First attempt
        headers = await self._auth.get_authorization_header()
        headers["content-type"] = "application/json"
        resp = await self._do_post(body, headers)

        # 401 recovery: the cached token went bad between header-build
        # and POST (rare race with concurrent refresh). Invalidate the
        # cache and retry exactly once.
        if resp.status_code == 401:
            logger.warning(
                "claude-backend-api: /v1/messages returned 401, invalidating "
                "auth cache and retrying once"
            )
            self._auth.invalidate_cache()
            headers = await self._auth.get_authorization_header()
            headers["content-type"] = "application/json"
            resp = await self._do_post(body, headers)

            if resp.status_code == 401:
                # Two consecutive 401s means the credential itself is bad.
                raise AuthError(
                    "Authentication failed twice in a row against "
                    "api.anthropic.com/v1/messages; token state may be "
                    "corrupt. Run 'claude auth login' to re-authenticate."
                )

        # Status code handling
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise BackendError(
                    f"Anthropic returned 200 but the body is not JSON: {exc}",
                    status=200,
                ) from exc

        # 429 = rate limited. Token is fine; propagate with retry hint.
        if resp.status_code == 429:
            retry_after_raw = resp.headers.get("retry-after")
            retry_after: float | None = None
            if retry_after_raw is not None:
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = None
            raise BackendError(
                f"Anthropic rate limit exceeded (429). "
                f"Retry after {retry_after_raw or 'unknown'} seconds.",
                status=429,
                retry_after=retry_after,
            )

        # 403 = scope rejected (should be impossible with user:inference but
        # surface it clearly if it happens).
        if resp.status_code == 403:
            raise AuthError(
                f"Anthropic returned 403 Forbidden. Token is valid but "
                f"lacks permission. Response: {resp.text[:500]}. "
                f"Run 'claude auth login' to re-authenticate with "
                f"the correct scopes."
            )

        # Everything else: regular BackendError with the status code.
        raise BackendError(
            f"Anthropic API error {resp.status_code}: {resp.text[:500]}",
            status=resp.status_code,
        )

    async def _do_post(self, body: dict, headers: dict[str, str]) -> httpx.Response:
        """Single httpx POST. Wraps network errors as :class:`BackendError`."""
        try:
            async with self._http_factory() as client:
                return await client.post(ANTHROPIC_MESSAGES_URL, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise BackendError(
                f"Anthropic request timed out: {exc}",
                status=None,
            ) from exc
        except httpx.RequestError as exc:
            raise BackendError(
                f"Anthropic request failed: {exc}",
                status=None,
            ) from exc
