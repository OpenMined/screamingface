"""Claude API proxy router — streaming and non-streaming support."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

if TYPE_CHECKING:
    from screamingface.plugins.claude_proxy.plugin import ClaudeProxySettings

logger = logging.getLogger(__name__)

FORWARD_HEADERS = {
    "anthropic-version",
    "anthropic-beta",
    "x-api-key",
    "content-type",
    "authorization",
    "accept",
}

# Keys whose values are redacted in trace output
_SENSITIVE_HEADERS = {"x-api-key", "authorization"}


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with sensitive values masked."""
    return {
        k: (v[:8] + "…" if k.lower() in _SENSITIVE_HEADERS and len(v) > 8 else v)
        for k, v in headers.items()
    }


def _fmt_headers(headers: dict[str, str]) -> str:
    return "\n".join(f"  {k}: {v}" for k, v in headers.items())


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more chars)"


def create_router(settings: ClaudeProxySettings) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    api_key_env = settings.api_key_env

    router = APIRouter(tags=["claude-proxy"])

    def _check_host(request: Request) -> None:
        """When intercept is active, only proxy requests to intercepted domains.

        Requests arriving with Host: api.anthropic.com are from intercepted
        clients. Requests with Host: localhost are direct and should not be
        caught by the proxy's catch-all routes.
        """
        intercept_domains: set[str] | None = getattr(request.app.state, "intercept_domains", None)
        if intercept_domains is None:
            return  # no intercept active — proxy everything
        host = request.headers.get("host", "").split(":")[0]
        if host not in intercept_domains:
            raise HTTPException(status_code=404)

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        # Auth fallback: inject API key from env if client didn't provide one
        if "x-api-key" not in headers and "authorization" not in headers:
            api_key = os.environ.get(api_key_env, "")
            if api_key:
                headers["x-api-key"] = api_key
        return headers

    def _trace_request(method: str, url: str, headers: dict[str, str], body: Any = None) -> None:
        parts = [
            f"→ {method} {url}",
            f"→ headers:\n{_fmt_headers(_redact_headers(headers))}",
        ]
        if body is not None:
            if isinstance(body, (dict, list)):
                parts.append(f"→ body:\n{_truncate(json.dumps(body, indent=2))}")
            elif isinstance(body, bytes) and body:
                parts.append(f"→ body:\n{_truncate(body.decode(errors='replace'))}")
        logger.info("\n".join(parts))

    def _trace_response(
        status: int, elapsed: float, headers: dict[str, str], body: str | None = None
    ) -> None:
        resp_hdrs = {k: v for k, v in headers.items()}
        parts = [
            f"← {status}  ({elapsed:.1f}s)",
            f"← headers:\n{_fmt_headers(resp_hdrs)}",
        ]
        if body is not None:
            parts.append(f"← body:\n{_truncate(body)}")
        logger.info("\n".join(parts))

    @router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
    async def proxy_messages(request: Request) -> Response:
        _check_host(request)
        body = await request.json()
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/messages"

        _trace_request("POST", url, headers, body)

        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        t0 = time.monotonic()

        stream = body.get("stream", False)

        if stream:
            client = httpx.AsyncClient(timeout=timeout)

            async def stream_response():
                chunks: list[bytes] = []
                try:
                    async with client.stream("POST", url, json=body, headers=headers) as resp:
                        logger.info(
                            "← %d streaming  (%.1fs to first byte)\n← headers:\n%s",
                            resp.status_code,
                            time.monotonic() - t0,
                            _fmt_headers(dict(resp.headers)),
                        )
                        async for chunk in resp.aiter_bytes():
                            chunks.append(chunk)
                            yield chunk
                finally:
                    if chunks:
                        raw = b"".join(chunks).decode(errors="replace")
                        logger.info("← streaming body:\n%s", _truncate(raw))
                    await client.aclose()

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
            elapsed = time.monotonic() - t0
            _trace_response(resp.status_code, elapsed, dict(resp.headers), resp.text)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

    @router.get("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_get")
    @router.post("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_post")
    async def proxy_catchall(request: Request, path: str) -> Response:
        _check_host(request)
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/{path}"
        method = request.method

        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        t0 = time.monotonic()

        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        _trace_request(method, url, headers, body if body else None)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)

        elapsed = time.monotonic() - t0
        _trace_response(resp.status_code, elapsed, dict(resp.headers), resp.text)

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return StreamingResponse(
                iter([resp.content]),
                media_type="text/event-stream",
                status_code=resp.status_code,
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    return router
