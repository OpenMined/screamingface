"""OpenAIBackend — direct HTTP POST to chatgpt.com/backend-api/codex/responses.

Uses ``curl_cffi`` with browser TLS impersonation to bypass Cloudflare's
bot detection on chatgpt.com. This is the same endpoint the Codex CLI
uses via WebSocket, but accessed over standard HTTP SSE streaming.

Two auth paths:
- ChatGPT OAuth (default): reads JWT from ``~/.codex/auth.json``,
  POSTs to ``chatgpt.com/backend-api/codex/responses``
- API key (``OPENAI_API_KEY`` env var): standard httpx POST to
  ``api.openai.com/v1/responses``
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import uuid

import certifi
import httpx

from screamingface.plugins.codex_backend_api.adapter import OpenAIResponsesAdapter
from screamingface.plugins.codex_backend_api.auth import CodexOAuth
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

# Standard public API (API-key auth only)
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

# ChatGPT backend (OAuth auth, requires curl_cffi for Cloudflare bypass)
CHATGPT_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"

# curl_cffi TLS profile that bypasses Cloudflare on chatgpt.com
CURL_CFFI_PROFILE = "chrome99_android"

# Default instructions (required by the chatgpt.com endpoint)
_DEFAULT_INSTRUCTIONS = (
    "You are a helpful assistant. Answer the user's question based only on "
    "the provided context. Be concise and factual."
)


class OpenAIBackend(Backend):
    """Dual-path backend: chatgpt.com (OAuth) or api.openai.com (API key)."""

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

    def _has_api_key(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    # ChatGPT backend path (curl_cffi + chatgpt.com)
    # ------------------------------------------------------------------

    def _chatgpt_post(
        self,
        url: str,
        body: dict,
        headers: dict[str, str],
        timeout: float = 300.0,
    ) -> tuple[int, str, dict]:
        """Synchronous POST via curl_cffi with Cloudflare bypass.

        Returns (status_code, response_text, response_headers).
        curl_cffi is sync-only; we call it from async via run_in_executor.
        """
        from curl_cffi.requests import Session

        with Session(impersonate=CURL_CFFI_PROFILE) as s:
            r = s.post(url, json=body, headers=headers, timeout=timeout)
            return r.status_code, r.text, dict(r.headers)

    async def _chatgpt_run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 16000,
        timeout_seconds: float = 300.0,
    ) -> CoreMessage:
        """POST to chatgpt.com/backend-api/codex/responses with ChatGPT JWT."""
        import asyncio

        headers = await self._auth.get_authorization_header()
        account_id = self._auth.get_account_id()
        session_id = str(uuid.uuid4())

        headers.update(
            {
                "chatgpt-account-id": account_id,
                "originator": "codex_exec",
                "session_id": session_id,
                "version": "0.120.0",
                "x-client-request-id": session_id,
                "x-codex-window-id": f"{session_id}:0",
                "accept": "text/event-stream",
                "content-type": "application/json",
            }
        )

        # Build the body — chatgpt.com requires "instructions"
        prompt_parts = []
        for msg in messages:
            if isinstance(msg.content, str):
                prompt_parts.append(msg.content)
            else:
                from screamingface.plugins.llm_base.messages import TextPart

                for part in msg.content:
                    if isinstance(part, TextPart):
                        prompt_parts.append(part.text)

        body: dict = {
            "model": model,
            "instructions": system or _DEFAULT_INSTRUCTIONS,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": t}],
                }
                for t in prompt_parts
            ],
            "store": False,
            "stream": True,
            "reasoning": {"effort": "high"},
            "text": {"verbosity": "low"},
            "client_metadata": {"x-codex-installation-id": str(uuid.uuid4())},
        }

        loop = asyncio.get_event_loop()
        status, text, resp_headers = await loop.run_in_executor(
            None, self._chatgpt_post, CHATGPT_RESPONSES_URL, body, headers, timeout_seconds
        )

        if status == 200:
            return self._parse_sse_response(text)

        if status == 429:
            raise BackendError("Codex rate limited (429)", status=429)
        if status in (401, 403):
            raise AuthError(
                f"ChatGPT backend rejected auth (HTTP {status}): {text[:300]}. "
                f"Run 'codex login' to re-authenticate."
            )
        raise BackendError(f"ChatGPT backend error {status}: {text[:500]}", status=status)

    @staticmethod
    def _parse_sse_response(sse_text: str) -> CoreMessage:
        """Parse SSE event stream from chatgpt.com into a CoreMessage."""
        from screamingface.plugins.llm_base.messages import TextPart

        text_parts: list[str] = []
        provider_metadata: dict = {}

        for line in sse_text.split("\n"):
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            event_type = data.get("type", "")
            if event_type == "response.output_text.delta":
                text_parts.append(data.get("delta", ""))
            elif event_type == "response.completed":
                resp = data.get("response", {})
                usage = resp.get("usage", {})
                if usage:
                    provider_metadata["openai.usage"] = usage
                provider_metadata["openai.model"] = resp.get("model", "")

        return CoreMessage(
            role="assistant",
            content=[TextPart(text="".join(text_parts))],
            provider_metadata=provider_metadata or None,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health(self, model: str = "gpt-5.4") -> HealthStatus:
        """Check auth validity via a minimal probe call."""
        if self._has_api_key():
            return await self._health_api_key(model)
        return await self._health_chatgpt()

    async def _health_chatgpt(self) -> HealthStatus:
        """Probe chatgpt.com/backend-api/codex/responses with a tiny call."""
        import asyncio

        try:
            headers = await self._auth.get_authorization_header()
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        account_id = self._auth.get_account_id()
        session_id = str(uuid.uuid4())
        headers.update(
            {
                "chatgpt-account-id": account_id,
                "originator": "codex_exec",
                "session_id": session_id,
                "version": "0.120.0",
                "x-client-request-id": session_id,
                "x-codex-window-id": f"{session_id}:0",
                "accept": "text/event-stream",
                "content-type": "application/json",
            }
        )

        body = {
            "model": "gpt-5.4",
            "instructions": "Say OK.",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "store": False,
            "stream": True,
            "reasoning": {"effort": "high"},
            "text": {"verbosity": "low"},
        }

        loop = asyncio.get_event_loop()
        try:
            status, text, _ = await loop.run_in_executor(
                None, self._chatgpt_post, CHATGPT_RESPONSES_URL, body, headers, 15.0
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

    async def _health_api_key(self, model: str) -> HealthStatus:
        """Probe api.openai.com with API key."""
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

        rate_limit = _extract_openai_rate_limits(resp.headers)
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
                error="rate limited",
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
            error=f"Unexpected status {resp.status_code}: {resp.text[:300]}",
            rate_limit=rate_limit,
        )

    # ------------------------------------------------------------------
    # run() — the main entry point
    # ------------------------------------------------------------------

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
        if not self._has_api_key():
            # ChatGPT OAuth → chatgpt.com/backend-api/codex/responses
            return await self._chatgpt_run(
                messages, model=model, system=system, timeout_seconds=timeout_seconds
            )

        # API key → standard api.openai.com/v1/responses
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

    # ------------------------------------------------------------------
    # API-key path helpers (httpx)
    # ------------------------------------------------------------------

    async def _post_with_retry(self, body: dict) -> dict:
        headers = await self._auth.get_authorization_header()
        headers["content-type"] = "application/json"
        resp = await self._do_post(body, headers)

        if resp.status_code == 401:
            self._auth.invalidate_cache()
            headers = await self._auth.get_authorization_header()
            headers["content-type"] = "application/json"
            resp = await self._do_post(body, headers)
            if resp.status_code == 401:
                raise AuthError("Authentication failed twice. Run 'codex login'.")

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after_raw = resp.headers.get("retry-after")
            retry_after = float(retry_after_raw) if retry_after_raw else None
            raise BackendError("Rate limited (429)", status=429, retry_after=retry_after)
        if resp.status_code == 403:
            raise AuthError(f"Forbidden (403): {resp.text[:300]}")
        raise BackendError(
            f"OpenAI error {resp.status_code}: {resp.text[:500]}",
            status=resp.status_code,
        )

    async def _do_post(self, body: dict, headers: dict[str, str]) -> httpx.Response:
        try:
            async with self._http_factory() as client:
                return await client.post(OPENAI_RESPONSES_URL, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise BackendError(f"Request timed out: {exc}", status=None) from exc
        except httpx.RequestError as exc:
            raise BackendError(f"Request failed: {exc}", status=None) from exc


def _extract_openai_rate_limits(headers: httpx.Headers) -> dict[str, str | int | float]:
    prefix = "x-ratelimit-"
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
    if "remaining_tokens" in result:
        result["tokens_remaining"] = result["remaining_tokens"]
    if "remaining_requests" in result:
        result["requests_remaining"] = result["remaining_requests"]
    return result
