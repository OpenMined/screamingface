"""OllamaBackend — direct httpx POST to a local (or remote) Ollama server.

Wires the three provider-stack pieces together:

1. :class:`OllamaAuth` returns an optional ``Authorization: Bearer`` header
   (empty dict when unauthenticated, which is the default for local Ollama).
2. :class:`OllamaAdapter` translates CoreMessage ↔ Ollama ``/api/chat`` body.
3. This module does the transport: ``httpx.AsyncClient.post()`` to
   ``{base_url}/api/chat`` with ``stream: False``, handles status codes,
   keeps the 401-retry path for auth-strategy contract parity.
"""

from __future__ import annotations

import logging

import httpx

from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition
from screamingface.plugins.ollama_backend_api.adapter import OllamaAdapter
from screamingface.plugins.ollama_backend_api.auth import OllamaAuth

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaBackend(Backend):
    """Direct-to-API backend for Ollama's native ``/api/chat`` endpoint.

    Args:
        base_url: Ollama server base URL (default ``http://localhost:11434``).
        auth: Auth strategy. Defaults to :class:`OllamaAuth` (no-op unless
            an ``OLLAMA_API_KEY`` env var or settings.api_key is set).
        adapter: Shape adapter. Defaults to :class:`OllamaAdapter`.
        http_client_factory: Callable returning an ``httpx.AsyncClient``.
            Tests inject a factory that returns a mocked client.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        auth: OllamaAuth | None = None,
        adapter: OllamaAdapter | None = None,
        http_client_factory=None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth or OllamaAuth()
        self._adapter = adapter or OllamaAdapter()
        self._http_factory = http_client_factory or self._default_http_factory

    @property
    def _chat_url(self) -> str:
        return f"{self._base_url}/api/chat"

    @property
    def _tags_url(self) -> str:
        return f"{self._base_url}/api/tags"

    @staticmethod
    def _default_http_factory():
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
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
        """Execute one non-streaming round-trip against Ollama."""
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
    # Transport helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(self, body: dict) -> dict:
        headers = await self._auth.get_authorization_header()
        headers["content-type"] = "application/json"
        resp = await self._do_post(body, headers)

        if resp.status_code == 401:
            # Keep the contract parity with the other backends even though
            # Ollama's no-auth path realistically never returns 401.
            self._auth.invalidate_cache()
            headers = await self._auth.get_authorization_header()
            headers["content-type"] = "application/json"
            resp = await self._do_post(body, headers)
            if resp.status_code == 401:
                raise AuthError(
                    "Authentication failed twice against Ollama. "
                    "Set OLLAMA_API_KEY or update plugin settings.api_key."
                )

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after_raw = resp.headers.get("retry-after")
            retry_after = float(retry_after_raw) if retry_after_raw else None
            raise BackendError("Ollama rate limited (429)", status=429, retry_after=retry_after)
        if resp.status_code == 403:
            raise AuthError(f"Ollama forbidden (403): {resp.text[:300]}")
        if resp.status_code == 404:
            raise BackendError(
                f"Ollama 404: {resp.text[:300]}. Is the model pulled? (ollama pull <model>)",
                status=404,
            )
        raise BackendError(
            f"Ollama error {resp.status_code}: {resp.text[:500]}",
            status=resp.status_code,
        )

    async def _do_post(self, body: dict, headers: dict[str, str]) -> httpx.Response:
        from screamingface.plugins.llm_base._tracing import (
            record_llm_call,
            set_provider_attrs,
            traced_provider_post,
        )

        with traced_provider_post("ollama", self._chat_url):
            try:
                async with self._http_factory() as client:
                    resp = await client.post(self._chat_url, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise BackendError(f"Request timed out: {exc}", status=None) from exc
            except httpx.RequestError as exc:
                raise BackendError(f"Request failed: {exc}", status=None) from exc
            set_provider_attrs(
                {"http.status_code": resp.status_code, "http.response.size": len(resp.content)}
            )
            record_llm_call("ollama", body, resp)
            return resp

    # ------------------------------------------------------------------
    # health()
    # ------------------------------------------------------------------

    async def health(self, model: str | None = None) -> HealthStatus:
        """Probe the Ollama server via ``GET /api/tags``.

        A successful response means the server is reachable and the
        (optional) auth header is accepted. Ollama's ``/api/tags`` does
        not report rate-limit capacity, so ``tokens_remaining`` /
        ``requests_remaining`` are left unset.
        """
        try:
            headers = await self._auth.get_authorization_header()
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        try:
            async with self._http_factory() as client:
                resp = await client.get(self._tags_url, headers=headers)
        except Exception as exc:
            return HealthStatus(authenticated=True, error=f"API unreachable: {exc}")

        if resp.status_code == 200:
            return HealthStatus(authenticated=True)
        if resp.status_code in (401, 403):
            return HealthStatus(
                authenticated=False,
                error=f"Ollama rejected auth (HTTP {resp.status_code}): {resp.text[:200]}",
            )
        return HealthStatus(
            authenticated=True,
            error=f"Unexpected status {resp.status_code}: {resp.text[:200]}",
        )
