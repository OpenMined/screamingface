"""OpenAIBackend -- raw httpx POST to api.openai.com/v1/responses.

Wires the three pieces of the provider stack together:

1. :class:`~codex_backend_api.auth.CodexOAuth` builds the headers
   (OAuth bearer from ~/.codex/auth.json).
2. :class:`~codex_backend_api.adapter.OpenAIResponsesAdapter` converts the
   incoming :class:`CoreMessage` list into an OpenAI Chat Completions
   request body and parses the response back.
3. This module does the transport: ``httpx.AsyncClient.post()`` to
   ``https://api.openai.com/v1/responses``, handles status codes,
   one-shot 401 retry path via auth cache invalidation.
"""

from __future__ import annotations

import logging
import ssl

import certifi
import httpx

from screamingface.plugins.codex_backend_api.adapter import OpenAIResponsesAdapter
from screamingface.plugins.codex_backend_api.auth import CodexOAuth
from screamingface.plugins.llm_base.backend_base import Backend
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAIBackend(Backend):
    """Direct-to-API backend for OpenAI's Chat Completions endpoint.

    Args:
        auth: The auth strategy to build headers with. Defaults to
            :class:`CodexOAuth` reading from ~/.codex/auth.json.
        adapter: The shape adapter to use. Defaults to
            :class:`OpenAIResponsesAdapter`.
        http_client_factory: Callable returning an ``httpx.AsyncClient``.
            Tests inject a factory that returns a mocked client.
    """

    def __init__(
        self,
        *,
        auth: CodexOAuth | None = None,
        adapter: OpenAIResponsesAdapter | None = None,
        http_client_factory=None,
    ) -> None:
        self._auth = auth or CodexOAuth()
        self._adapter = adapter or OpenAIResponsesAdapter()
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
        """Execute one non-streaming round-trip against OpenAI.

        Flow:

        1. Build the outbound request body via the adapter.
        2. Get auth headers from :class:`CodexOAuth`.
        3. POST to ``/v1/responses``.
        4. On 401: invalidate auth cache, retry exactly once.
        5. On 200: parse via the adapter, return the CoreMessage.
        6. On any other error status: raise :class:`BackendError`.
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
        """POST with the one-shot 401-retry recovery path."""
        headers = await self._auth.get_authorization_header()
        headers["content-type"] = "application/json"
        resp = await self._do_post(body, headers)

        if resp.status_code == 401:
            logger.warning(
                "codex-backend-api: /v1/responses returned 401, "
                "invalidating auth cache and retrying once"
            )
            self._auth.invalidate_cache()
            headers = await self._auth.get_authorization_header()
            headers["content-type"] = "application/json"
            resp = await self._do_post(body, headers)

            if resp.status_code == 401:
                raise AuthError(
                    "Authentication failed twice in a row against "
                    "api.openai.com/v1/responses; token state may be "
                    "corrupt. Run 'codex auth login' to re-authenticate."
                )

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise BackendError(
                    f"OpenAI returned 200 but the body is not JSON: {exc}",
                    status=200,
                ) from exc

        if resp.status_code == 429:
            retry_after_raw = resp.headers.get("retry-after")
            retry_after: float | None = None
            if retry_after_raw is not None:
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = None
            raise BackendError(
                f"OpenAI rate limit exceeded (429). "
                f"Retry after {retry_after_raw or 'unknown'} seconds.",
                status=429,
                retry_after=retry_after,
            )

        if resp.status_code == 403:
            raise AuthError(
                f"OpenAI returned 403 Forbidden. Token is valid but "
                f"lacks permission. Response: {resp.text[:500]}. "
                f"Run 'codex auth login' to re-authenticate with "
                f"the correct scopes."
            )

        raise BackendError(
            f"OpenAI API error {resp.status_code}: {resp.text[:500]}",
            status=resp.status_code,
        )

    async def _do_post(self, body: dict, headers: dict[str, str]) -> httpx.Response:
        """Single httpx POST. Wraps network errors as :class:`BackendError`."""
        try:
            async with self._http_factory() as client:
                return await client.post(OPENAI_RESPONSES_URL, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise BackendError(
                f"OpenAI request timed out: {exc}",
                status=None,
            ) from exc
        except httpx.RequestError as exc:
            raise BackendError(
                f"OpenAI request failed: {exc}",
                status=None,
            ) from exc
