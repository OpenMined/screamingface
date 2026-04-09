"""GeminiBackend — httpx POST to generativelanguage.googleapis.com."""

from __future__ import annotations

import logging
import ssl

import certifi
import httpx

from screamingface.plugins.gemini_backend_api.adapter import GeminiAdapter
from screamingface.plugins.gemini_backend_api.auth import GeminiAuth
from screamingface.plugins.llm_base.backend_base import Backend
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiBackend(Backend):
    def __init__(
        self,
        *,
        auth: GeminiAuth | None = None,
        adapter: GeminiAdapter | None = None,
        http_client_factory=None,
    ) -> None:
        self._auth = auth or GeminiAuth()
        self._adapter = adapter or GeminiAdapter()
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
        body = self._adapter.to_provider_format(
            messages,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Extract model from body (adapter stores it as _model)
        api_model = body.pop("_model", model)
        url = f"{GEMINI_API_BASE}/models/{api_model}:generateContent"

        response_data = await self._post_with_retry(body, url)
        return self._adapter.from_provider_response(response_data)

    async def _post_with_retry(self, body: dict, url: str) -> dict:
        headers = await self._auth.get_authorization_header()
        headers["content-type"] = "application/json"
        resp = await self._do_post(body, headers, url)

        if resp.status_code == 401:
            logger.warning("gemini-backend-api: 401, retrying once")
            self._auth.invalidate_cache()
            headers = await self._auth.get_authorization_header()
            headers["content-type"] = "application/json"
            resp = await self._do_post(body, headers, url)
            if resp.status_code == 401:
                raise AuthError(
                    "Authentication failed twice against Google AI API. Check your GOOGLE_API_KEY."
                )

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise BackendError(
                    f"Gemini returned 200 but body is not JSON: {exc}",
                    status=200,
                ) from exc

        if resp.status_code == 429:
            retry_after_raw = resp.headers.get("retry-after")
            retry_after: float | None = None
            if retry_after_raw:
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = None
            raise BackendError(
                "Gemini rate limit exceeded (429).",
                status=429,
                retry_after=retry_after,
            )

        if resp.status_code == 403:
            raise AuthError(f"Gemini returned 403 Forbidden: {resp.text[:500]}")

        raise BackendError(
            f"Gemini API error {resp.status_code}: {resp.text[:500]}",
            status=resp.status_code,
        )

    async def _do_post(self, body: dict, headers: dict[str, str], url: str) -> httpx.Response:
        try:
            async with self._http_factory() as client:
                return await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise BackendError(f"Gemini request timed out: {exc}", status=None) from exc
        except httpx.RequestError as exc:
            raise BackendError(f"Gemini request failed: {exc}", status=None) from exc
