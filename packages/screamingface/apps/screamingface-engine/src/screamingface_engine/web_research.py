"""Private SearXNG search and safe public-page extraction adapter."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any, NoReturn
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from url4 import ResolutionError

type HostResolver = Callable[[str], Awaitable[Sequence[str]]]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_TEXT_MEDIA_TYPES = frozenset({"text/html", "text/plain", "application/xhtml+xml"})
_MAX_REDIRECTS = 3
_BLOCKED_URL_PREFIXES = (
    ("huggingface.co", "/datasets/perplexity-ai/draco"),
    ("openrouter.ai", "/blog/announcements/fusion-beats-frontier"),
    ("paperswithcode.com", "/dataset/draco"),
    ("arxiv.org", "/abs/2509"),
)


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class WebResearchClient:
    """One reusable client for SearXNG discovery and bounded page reads."""

    def __init__(
        self,
        searxng_url: str,
        *,
        timeout: float,
        max_results: int,
        max_content_chars: int,
        max_fetch_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: HostResolver | None = None,
    ) -> None:
        self._searxng_url = searxng_url.rstrip("/")
        self._timeout = timeout
        self._max_results = max_results
        self._max_content_chars = max_content_chars
        self._max_fetch_bytes = max_fetch_bytes
        self._transport = transport
        self._resolver = resolver or _resolve_addresses
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def start(self) -> None:
        await self._get_client()

    async def aclose(self) -> None:
        async with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            await client.aclose()

    async def search(self, query: str) -> tuple[SearchResult, ...]:
        if not isinstance(query, str) or not query.strip():
            _invalid("web_search requires a non-empty query")
        client = await self._get_client()
        try:
            response = await client.get(
                f"{self._searxng_url}/search",
                params={"q": query.strip(), "format": "json"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ResolutionError("SearXNG timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise ResolutionError(f"SearXNG returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ResolutionError(f"SearXNG request failed: {exc}") from exc

        payload = _json_object(response, "SearXNG")
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise ResolutionError("SearXNG response has no results array")
        results: list[SearchResult] = []
        for position, raw in enumerate(raw_results, 1):
            result = _search_result(raw, position)
            if _safe_result_url(result.url):
                results.append(result)
            if len(results) == self._max_results:
                break
        return tuple(results)

    async def fetch(self, url: str) -> str:
        current = url
        client = await self._get_client()
        for redirects in range(_MAX_REDIRECTS + 1):
            await self._validate_public_url(current)
            try:
                async with client.stream(
                    "GET",
                    current,
                    headers={
                        "accept": "text/html,text/plain,application/xhtml+xml",
                        "user-agent": "screamingface-engine/0.1 web-research",
                    },
                    follow_redirects=False,
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise ResolutionError("web_fetch redirect has no location")
                        if redirects == _MAX_REDIRECTS:
                            raise ResolutionError("web_fetch exceeded the redirect limit")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if media_type not in _TEXT_MEDIA_TYPES:
                        raise ResolutionError(
                            f"web_fetch received unsupported content type {media_type!r}"
                        )
                    body = await _bounded_body(response, self._max_fetch_bytes)
            except httpx.TimeoutException as exc:
                raise ResolutionError("web_fetch timed out") from exc
            except httpx.HTTPStatusError as exc:
                raise ResolutionError(
                    f"web_fetch returned HTTP {exc.response.status_code}"
                ) from exc
            except httpx.RequestError as exc:
                raise ResolutionError(f"web_fetch request failed: {exc}") from exc
            return _readable_text(body, media_type)[: self._max_content_chars]
        raise AssertionError("redirect loop must return or raise")

    async def _validate_public_url(self, url: str) -> None:
        parsed = _parsed_public_url(url)
        assert parsed.hostname is not None
        try:
            addresses = await self._resolver(parsed.hostname)
        except OSError as exc:
            raise ResolutionError(f"web_fetch could not resolve {parsed.hostname!r}") from exc
        if not addresses:
            raise ResolutionError(f"web_fetch could not resolve {parsed.hostname!r}")
        for address in addresses:
            if not _public_address(address):
                _invalid("web_fetch target must resolve only to the public network")

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                )
            return self._client


def _json_object(response: httpx.Response, label: str) -> Mapping[str, Any]:
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise ResolutionError(f"{label} returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ResolutionError(f"{label} returned an invalid response")
    return payload


def _search_result(value: object, position: int) -> SearchResult:
    if not isinstance(value, Mapping):
        raise ResolutionError(f"SearXNG result {position} must be an object")
    title = value.get("title")
    url = value.get("url")
    snippet = value.get("content")
    if not all(isinstance(item, str) and item.strip() for item in (title, url, snippet)):
        raise ResolutionError(f"SearXNG result {position} has invalid title, URL, or content")
    assert isinstance(title, str) and isinstance(url, str) and isinstance(snippet, str)
    return SearchResult(title.strip(), url.strip(), snippet.strip())


def _safe_result_url(url: str) -> bool:
    try:
        _parsed_public_url(url)
    except ResolutionError:
        return False
    return True


def _parsed_public_url(url: str):
    if not isinstance(url, str) or not url.strip():
        _invalid("web_fetch requires a non-empty URL")
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _invalid("web_fetch URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        _invalid("web_fetch URL must not contain credentials")
    try:
        parsed.port
    except ValueError:
        _invalid("web_fetch URL has an invalid port")
    if _blocked_url(parsed.hostname, parsed.path):
        _invalid("web_fetch URL is blocked by the benchmark contamination policy")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return parsed
    if not address.is_global:
        _invalid("web_fetch target must resolve only to the public network")
    return parsed


def _blocked_url(host: str, path: str) -> bool:
    normalized_host = host.rstrip(".").lower()
    normalized_path = unquote(path).lower()
    return any(
        normalized_host == blocked_host and normalized_path.startswith(blocked_path)
        for blocked_host, blocked_path in _BLOCKED_URL_PREFIXES
    )


def _public_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


async def _resolve_addresses(host: str) -> tuple[str, ...]:
    records = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
    return tuple(dict.fromkeys(str(record[4][0]) for record in records))


async def _bounded_body(response: httpx.Response, maximum: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > maximum:
                raise ResolutionError("web_fetch exceeded the maximum response size")
        except ValueError:
            raise ResolutionError("web_fetch received an invalid content length") from None
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > maximum:
            raise ResolutionError("web_fetch exceeded the maximum response size")
    return bytes(body)


class _TextExtractor(HTMLParser):
    _SKIPPED = frozenset({"script", "style", "noscript", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._SKIPPED:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def _readable_text(body: bytes, media_type: str) -> str:
    source = body.decode("utf-8", errors="replace")
    if media_type == "text/plain":
        return " ".join(source.split())
    parser = _TextExtractor()
    parser.feed(source)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["SearchResult", "WebResearchClient"]
