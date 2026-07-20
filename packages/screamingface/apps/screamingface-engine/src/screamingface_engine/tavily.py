"""Process-local Tavily connection and bounded search/extract adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import NoReturn

import httpx
from url4 import ResolutionError

from screamingface_engine.connection_contract import (
    ConnectionControlError,
    parse_unique_json_object,
)
from screamingface_engine.tool_policy import ExtractPolicy, SearchPolicy

TAVILY_BASE_URL = "https://api.tavily.com"
TAVILY_PROVIDER_ID = "tavily"
MAX_TAVILY_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_NORMALIZED_TOOL_BYTES = 1024 * 1024
_ATTEMPTS = 3
_RETRY_DELAYS = (2.0, 4.0)

type Sleep = Callable[[float], Awaitable[None]]


class TavilyService:
    """Own one local credential and all Tavily HTTP behavior for the engine."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        self._sleep = sleep
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

    async def is_connected(self) -> bool:
        async with self._state_lock:
            return self._api_key is not None

    async def set_api_key(self, api_key: str) -> dict[str, object]:
        # INVARIANT: A failed candidate never destroys the last validated credential.
        await self._validate(api_key)
        async with self._state_lock:
            self._api_key = api_key
        return await self.get_public()

    async def disconnect(self) -> None:
        async with self._state_lock:
            self._api_key = None

    async def search(self, query: str, policy: SearchPolicy) -> dict[str, object]:
        payload = await self._execute("/search", policy.request_body(query))
        return _search_result(payload, policy)

    async def extract(
        self,
        url: str,
        policy: ExtractPolicy,
        *,
        query: str | None,
    ) -> dict[str, object]:
        payload = await self._execute("/extract", policy.request_body(url, query=query))
        return _extract_result(payload, policy, url)

    async def aclose(self) -> None:
        async with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            await client.aclose()

    async def _validate(self, api_key: str) -> None:
        try:
            response, body = await self._send("GET", "/usage", api_key=api_key)
        except ResolutionError as exc:
            raise ConnectionControlError(
                502,
                "invalid_provider_response",
                "Tavily returned an invalid validation response.",
                provider=TAVILY_PROVIDER_ID,
                retryable=True,
            ) from exc
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
            payload = parse_unique_json_object(body.decode())
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

    async def _execute(self, path: str, request_body: Mapping[str, object]) -> dict[str, object]:
        api_key = await self._required_key()
        for attempt in range(_ATTEMPTS):
            try:
                response, body = await self._send(
                    "POST", path, api_key=api_key, json_body=request_body
                )
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt + 1 < _ATTEMPTS:
                    await self._sleep(_RETRY_DELAYS[attempt])
                    continue
                raise ResolutionError(
                    "Tavily is temporarily unavailable.",
                    code="provider_unavailable",
                ) from exc
            if response.status_code in {401, 403}:
                await self._invalidate(api_key)
                _resolution(
                    "Tavily authentication is required.",
                    "authentication_required",
                    permanent=True,
                )
            if response.status_code == 400:
                _resolution(
                    "Tavily rejected the tool request.", "invalid_tool_request", permanent=True
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < _ATTEMPTS:
                    await self._sleep(_RETRY_DELAYS[attempt])
                    continue
                code = "rate_limited" if response.status_code == 429 else "provider_unavailable"
                message = (
                    "Tavily rate limit reached; retry later."
                    if code == "rate_limited"
                    else "Tavily is temporarily unavailable."
                )
                _resolution(message, code)
            if response.status_code != 200:
                _resolution(
                    "Tavily rejected the tool request.", "invalid_tool_request", permanent=True
                )
            try:
                return parse_unique_json_object(body.decode())
            except (TypeError, UnicodeDecodeError, ValueError) as exc:
                raise ResolutionError(
                    "Tavily returned an invalid response.",
                    code="invalid_provider_response",
                ) from exc
        raise AssertionError("bounded Tavily retry loop exhausted without a result")

    async def _required_key(self) -> str:
        async with self._state_lock:
            api_key = self._api_key
        if api_key is None:
            _resolution(
                "Connect Tavily before using benchmark tools.",
                "authentication_required",
                permanent=True,
            )
        return api_key

    async def _invalidate(self, rejected_key: str) -> None:
        async with self._state_lock:
            if self._api_key == rejected_key:
                self._api_key = None

    async def _send(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        json_body: Mapping[str, object] | None = None,
    ) -> tuple[httpx.Response, bytes]:
        client = await self._get_client()
        request = client.build_request(
            method,
            path,
            headers={"Authorization": f"Bearer {api_key}"},
            json=json_body,
        )
        response = await client.send(request, stream=True)
        return response, await _bounded_body(response)

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
                raise ResolutionError(
                    "Tavily returned an oversized response.",
                    code="invalid_provider_response",
                )
            chunks.append(chunk)
    finally:
        await response.aclose()
    return b"".join(chunks)


def _search_result(payload: Mapping[str, object], policy: SearchPolicy) -> dict[str, object]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        _invalid_response("Tavily search response has no results list")
    truncated = len(raw_results) > policy.max_results
    results: list[dict[str, object]] = []
    for raw in raw_results[: policy.max_results]:
        if not isinstance(raw, Mapping):
            _invalid_response("Tavily search result is not an object")
        result, clipped = _search_item(raw, policy)
        truncated = truncated or clipped
        results.append(result)
    answer, clipped = _optional_text(payload.get("answer"), 50_000, "answer")
    truncated = truncated or clipped
    result_payload: dict[str, object] = {
        "answer": answer if policy.include_answer else None,
        "results": results,
    }
    if policy.include_images:
        images, clipped = _images(payload.get("images"), policy.include_image_descriptions)
        result_payload["images"] = images
        truncated = truncated or clipped
    if policy.include_usage:
        result_payload["usage"] = _usage(payload.get("usage"))
    result_payload["truncated"] = truncated
    return _fit(result_payload)


def _search_item(raw: Mapping[str, object], policy: SearchPolicy) -> tuple[dict[str, object], bool]:
    title, title_cut = _required_text(raw.get("title"), 2_000, "search title")
    url, url_cut = _required_text(raw.get("url"), 8_000, "search URL")
    content, content_cut = _required_text(raw.get("content"), 20_000, "search content")
    score = raw.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        _invalid_response("Tavily search score is invalid")
    result: dict[str, object] = {"title": title, "url": url, "content": content, "score": score}
    clipped = title_cut or url_cut or content_cut
    if policy.include_raw_content:
        raw_content, cut = _optional_text(raw.get("raw_content"), 20_000, "raw_content")
        result["raw_content"] = raw_content
        clipped = clipped or cut
    if policy.include_favicon:
        favicon, cut = _optional_text(raw.get("favicon"), 8_000, "favicon")
        result["favicon"] = favicon
        clipped = clipped or cut
    return result, clipped


def _extract_result(
    payload: Mapping[str, object], policy: ExtractPolicy, requested_url: str
) -> dict[str, object]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        _invalid_response("Tavily extract response has no results list")
    raw = raw_results[0] if raw_results else {"url": requested_url, "raw_content": ""}
    if not isinstance(raw, Mapping):
        _invalid_response("Tavily extract result is not an object")
    url, url_cut = _required_text(raw.get("url"), 8_000, "extract URL")
    content, content_cut = _required_text(
        raw.get("raw_content"), MAX_NORMALIZED_TOOL_BYTES - 1024, "extract content"
    )
    result: dict[str, object] = {"url": url, "content": content}
    clipped = url_cut or content_cut
    if policy.include_images:
        images, cut = _images(raw.get("images"), descriptions=False)
        result["images"] = images
        clipped = clipped or cut
    if policy.include_favicon:
        favicon, cut = _optional_text(raw.get("favicon"), 8_000, "favicon")
        result["favicon"] = favicon
        clipped = clipped or cut
    if policy.include_usage:
        result["usage"] = _usage(payload.get("usage"))
    result["truncated"] = clipped
    return _fit(result)


def _images(value: object, descriptions: bool) -> tuple[list[dict[str, str]], bool]:
    if value is None:
        return [], False
    if not isinstance(value, list):
        _invalid_response("Tavily images value is invalid")
    result: list[dict[str, str]] = []
    clipped = len(value) > 20
    for raw in value[:20]:
        if not isinstance(raw, Mapping):
            _invalid_response("Tavily image is not an object")
        url, cut = _required_text(raw.get("url"), 8_000, "image URL")
        item = {"url": url}
        clipped = clipped or cut
        if descriptions:
            description, cut = _required_text(raw.get("description"), 2_000, "image description")
            item["description"] = description
            clipped = clipped or cut
        result.append(item)
    return result, clipped


def _usage(value: object) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        _invalid_response("Tavily usage value is invalid")
    credits = value.get("credits")
    if isinstance(credits, bool) or not isinstance(credits, (int, float)):
        _invalid_response("Tavily usage credits are invalid")
    return {"credits": credits}


def _fit(payload: dict[str, object]) -> dict[str, object]:
    if len(_encoded(payload)) <= MAX_NORMALIZED_TOOL_BYTES:
        return payload
    # WHY: Drop optional high-volume enrichment before shrinking core evidence.
    payload.pop("images", None)
    results = payload.get("results")
    if isinstance(results, list):
        for value in results:
            if isinstance(value, dict):
                value.pop("raw_content", None)
                value.pop("favicon", None)
    payload["truncated"] = True
    if len(_encoded(payload)) > MAX_NORMALIZED_TOOL_BYTES:
        _invalid_response("normalized Tavily result exceeds the engine limit")
    return payload


def _encoded(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def _required_text(value: object, maximum: int, label: str) -> tuple[str, bool]:
    if not isinstance(value, str):
        _invalid_response(f"Tavily {label} is invalid")
    return _bounded_text(value, maximum)


def _optional_text(value: object, maximum: int, label: str) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if not isinstance(value, str):
        _invalid_response(f"Tavily {label} is invalid")
    return _bounded_text(value, maximum)


def _bounded_text(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode()
    if len(encoded) <= maximum:
        return value, False
    return encoded[:maximum].decode(errors="ignore"), True


def _invalid_response(message: str) -> NoReturn:
    raise ResolutionError(message, code="invalid_provider_response")


def _resolution(message: str, code: str, *, permanent: bool = False) -> NoReturn:
    raise ResolutionError(message, code=code, permanent=permanent)


__all__ = [
    "MAX_NORMALIZED_TOOL_BYTES",
    "MAX_TAVILY_RESPONSE_BYTES",
    "TAVILY_BASE_URL",
    "TAVILY_PROVIDER_ID",
    "TavilyService",
]
