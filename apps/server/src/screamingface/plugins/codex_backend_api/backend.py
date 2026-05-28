"""OpenAIBackend — direct HTTP POST to chatgpt.com or api.openai.com.

Two auth paths, dispatched by ``OPENAI_API_KEY``:

- **API key set** → standard ``api.openai.com/v1/responses`` over httpx.
- **No API key** → ``chatgpt.com/backend-api/codex/responses`` via
  ``curl_cffi`` (Cloudflare bypass) with the ChatGPT OAuth JWT.

This file is intentionally short: it only dispatches and maps errors.
The heavy machinery lives in:

- :mod:`.chatgpt_session` — curl_cffi POST, header / body builders.
- :mod:`.sse_parser` — turn an SSE stream into a :class:`CoreMessage`.
- :mod:`.rate_limits` — parse OpenAI's ``x-ratelimit-*`` headers.
"""

from __future__ import annotations

import asyncio
import logging
import os

from screamingface.plugins.codex_backend_api.adapter import OpenAIResponsesAdapter
from screamingface.plugins.codex_backend_api.auth import CodexOAuth
from screamingface.plugins.codex_backend_api.chatgpt_session import (
    CHATGPT_RESPONSES_URL,
    auth_headers_for,
    build_chatgpt_headers,
    build_health_probe_body,
    build_responses_body,
    post_responses_sync,
)
from screamingface.plugins.codex_backend_api.rate_limits import extract_openai_rate_limits
from screamingface.plugins.codex_backend_api.sse_parser import parse_responses_sse
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.backend_base import (
    Backend,
    HealthStatus,
    post_with_default_retry,
)
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.http import default_http_factory
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAIBackend(Backend):
    """Dual-path backend: chatgpt.com (OAuth) or api.openai.com (API key)."""

    def __init__(
        self,
        *,
        auth: CodexOAuth | None = None,
        adapter: OpenAIResponsesAdapter | None = None,
        http_client_factory=None,
        aigw_source: AigwTokenSource | None = None,
    ) -> None:
        self._auth = auth or CodexOAuth(aigw_source=aigw_source)
        self._adapter = adapter or OpenAIResponsesAdapter()
        self._http_factory = http_client_factory or default_http_factory

    def _has_api_key(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

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
        """Execute one round-trip against OpenAI."""
        if self._has_api_key():
            return await self._run_api_key(
                messages,
                model=model,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return await self._run_chatgpt(
            messages, model=model, system=system, timeout_seconds=timeout_seconds
        )

    async def health(self, model: str = "gpt-5.4") -> HealthStatus:
        if self._has_api_key():
            return await self._health_api_key(model)
        return await self._health_chatgpt()

    # ------------------------------------------------------------------
    # ChatGPT path
    # ------------------------------------------------------------------

    async def _run_chatgpt(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None,
        timeout_seconds: float,
    ) -> CoreMessage:
        try:
            auth_headers, account_id = await auth_headers_for(self._auth)
        except Exception as exc:
            raise AuthError(f"ChatGPT OAuth header error: {exc}") from exc

        headers = build_chatgpt_headers(auth_headers, account_id)
        body = build_responses_body(messages, model=model, system=system)

        loop = asyncio.get_event_loop()
        status, text, _ = await loop.run_in_executor(
            None, post_responses_sync, body, headers, timeout_seconds, CHATGPT_RESPONSES_URL
        )

        if status == 200:
            return parse_responses_sse(text)
        if status == 429:
            raise BackendError("Codex rate limited (429)", status=429)
        if status in (401, 403):
            raise AuthError(
                f"ChatGPT backend rejected auth (HTTP {status}): {text[:300]}. "
                f"Run 'codex login' to re-authenticate."
            )
        raise BackendError(f"ChatGPT backend error {status}: {text[:500]}", status=status)

    async def _health_chatgpt(self) -> HealthStatus:
        try:
            auth_headers, account_id = await auth_headers_for(self._auth)
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        headers = build_chatgpt_headers(auth_headers, account_id)
        body = build_health_probe_body()

        loop = asyncio.get_event_loop()
        try:
            status, text, _ = await loop.run_in_executor(
                None, post_responses_sync, body, headers, 15.0, CHATGPT_RESPONSES_URL
            )
        except Exception as exc:
            return HealthStatus(authenticated=True, error=f"API unreachable: {exc}")

        if status == 200:
            return HealthStatus(authenticated=True)
        if status == 429:
            return HealthStatus(authenticated=True, error="rate limited")
        if status in (401, 403):
            return HealthStatus(authenticated=False, error=f"HTTP {status}: {text[:200]}")
        return HealthStatus(authenticated=True, error=f"HTTP {status}: {text[:200]}")

    # ------------------------------------------------------------------
    # API-key path
    # ------------------------------------------------------------------

    async def _run_api_key(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None,
        tools: list[ToolDefinition] | None,
        max_tokens: int,
        temperature: float | None,
    ) -> CoreMessage:
        body = self._adapter.to_provider_format(
            messages,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response_data = await post_with_default_retry(
            auth=self._auth,
            http_factory=self._http_factory,
            url=OPENAI_RESPONSES_URL,
            body=body,
            provider_name="OpenAI",
            auth_login_cmd="codex login",
        )
        return self._adapter.from_provider_response(response_data)

    async def _health_api_key(self, model: str) -> HealthStatus:
        try:
            headers = await self._auth.get_authorization_header()
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        headers["content-type"] = "application/json"
        body = {
            "model": model,
            "max_output_tokens": 1,
            "input": [{"role": "user", "content": "hi"}],
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(OPENAI_RESPONSES_URL, json=body, headers=headers)
        except Exception as exc:
            return HealthStatus(authenticated=True, error=f"API unreachable: {exc}")

        rate_limit = extract_openai_rate_limits(resp.headers)
        tokens_remaining = rate_limit.get("tokens_remaining")
        requests_remaining = rate_limit.get("requests_remaining")
        tr = int(tokens_remaining) if tokens_remaining is not None else None
        rr = int(requests_remaining) if requests_remaining is not None else None

        if resp.status_code == 200:
            return HealthStatus(
                authenticated=True,
                tokens_remaining=tr,
                requests_remaining=rr,
                rate_limit=rate_limit,
            )
        if resp.status_code == 429:
            return HealthStatus(
                authenticated=True,
                error="rate limited",
                tokens_remaining=tr,
                requests_remaining=rr,
                rate_limit=rate_limit,
            )
        if resp.status_code in (401, 403):
            return HealthStatus(
                authenticated=False,
                error=f"API rejected token (HTTP {resp.status_code}): {resp.text[:300]}",
            )
        return HealthStatus(
            authenticated=True,
            error=f"Unexpected status {resp.status_code}: {resp.text[:300]}",
            rate_limit=rate_limit,
        )
