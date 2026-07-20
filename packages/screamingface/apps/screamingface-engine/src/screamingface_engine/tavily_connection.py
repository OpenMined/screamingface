"""Process-local Tavily credential validation owned by ScreamingFace engine."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx

from screamingface_engine.connection_contract import (
    ConnectionControlError,
    parse_unique_json_object,
)

TAVILY_BASE_URL = "https://api.tavily.com"
TAVILY_PROVIDER_ID = "tavily"
MAX_TAVILY_RESPONSE_BYTES = 262_144


class TavilyConnection:
    """Validate and retain one researcher-owned Tavily key for this process."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._api_key: str | None = None

    async def get_public(self) -> dict[str, object]:
        async with self._state_lock:
            connected = self._api_key is not None
        return {
            "provider": TAVILY_PROVIDER_ID,
            "status": "connected" if connected else "not_connected",
            "auth_method": "api_key" if connected else None,
            "account_label": None,
        }

    async def set_api_key(self, api_key: str) -> dict[str, object]:
        # INVARIANT: A failed candidate never destroys the last validated credential.
        async with self._state_lock:
            await self._validate(api_key)
            self._api_key = api_key
        return await self.get_public()

    async def disconnect(self) -> None:
        async with self._state_lock:
            self._api_key = None

    async def aclose(self) -> None:
        async with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            await client.aclose()

    async def _validate(self, api_key: str) -> None:
        client = await self._get_client()
        try:
            request = client.build_request(
                "GET",
                "/usage",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response = await client.send(request, stream=True)
            body = await _bounded_body(response)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise ConnectionControlError(
                503,
                "provider_unavailable",
                "Tavily is temporarily unavailable.",
                provider=TAVILY_PROVIDER_ID,
                retryable=True,
            ) from exc
        if response.status_code in {401, 403}:
            raise ConnectionControlError(
                401,
                "invalid_credentials",
                "The Tavily API key is invalid.",
                provider=TAVILY_PROVIDER_ID,
            )
        if response.status_code == 429:
            raise ConnectionControlError(
                429,
                "rate_limited",
                "Tavily rate limit reached; retry later.",
                provider=TAVILY_PROVIDER_ID,
                retryable=True,
            )
        if response.status_code != 200:
            raise ConnectionControlError(
                503,
                "provider_unavailable",
                "Tavily is temporarily unavailable.",
                provider=TAVILY_PROVIDER_ID,
                retryable=True,
            )
        try:
            payload = parse_unique_json_object(body.decode("utf-8"))
            if not isinstance(payload.get("key"), Mapping) or not isinstance(
                payload.get("account"), Mapping
            ):
                raise TypeError("Tavily usage response is missing key or account")
        except (TypeError, UnicodeDecodeError, ValueError) as exc:
            raise ConnectionControlError(
                502,
                "invalid_provider_response",
                "Tavily returned an invalid validation response.",
                provider=TAVILY_PROVIDER_ID,
                retryable=True,
            ) from exc

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=TAVILY_BASE_URL,
                    timeout=self._timeout,
                    follow_redirects=False,
                    transport=self._transport,
                )
            return self._client


async def _bounded_body(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_TAVILY_RESPONSE_BYTES:
                raise ConnectionControlError(
                    502,
                    "invalid_provider_response",
                    "Tavily returned an invalid validation response.",
                    provider=TAVILY_PROVIDER_ID,
                    retryable=True,
                )
            chunks.append(chunk)
    finally:
        await response.aclose()
    return b"".join(chunks)


__all__ = ["MAX_TAVILY_RESPONSE_BYTES", "TAVILY_BASE_URL", "TavilyConnection"]
